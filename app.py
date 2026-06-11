"""词汇笔记本 — FastAPI 后端"""
import asyncio
import csv
import html as html_mod
import io
import json
import os
import re
import socket
import threading
import uuid
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fpdf import FPDF

import config

# ─── App ──────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_queue, _enrich_queue
    # 启动时校验配置
    try:
        provider = config.get_provider()
        print(f"  [config] provider: {provider}")
    except RuntimeError as e:
        print(f"  [config] 配置错误：{e}")
        raise
    _event_queue = asyncio.Queue()
    _enrich_queue = asyncio.Queue()
    worker_task = asyncio.create_task(_enrich_worker())
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Vocabulary Notebook", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Config ───────────────────────────────────────────────

DATA_FILE = Path("words.json")
CHINA_TZ = timezone(timedelta(hours=8))
STATIC_DIR = Path("frontend/dist")

# SSE 事件总线 — 后台 enrichment 完成后通知前端
# 必须在 startup 事件中初始化，否则 asyncio.Queue() 会绑定到错误的 event loop（Python 3.9）
_event_queue = None

# 补全任务队列 — 单 worker 串行消费，避免 Ollama 并发排队超时
_enrich_queue: Optional[asyncio.Queue] = None
# word_id → 上次尝试时间戳，冷却期内不重复入队
_enriching_ids: dict[str, float] = {}
_ENRICH_COOLDOWN = 300  # 秒


# ─── PDF 字体路径 (fpdf2 纯 Python，零系统依赖) ──────────

_CJK_FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
if not os.path.exists(_CJK_FONT_PATH):
    _CJK_FONT_PATH = None  # 兜底：中文显示为空白，但不会崩溃


# RLock 允许同一线程重入，_enrich_in_background 可在锁内 load+save
_write_lock = threading.RLock()


def load_words() -> dict:
    """读取 words.json，不存在时初始化，损坏时备份并返回空数据"""
    with _write_lock:
        if not DATA_FILE.exists():
            save_words({"words": []})
            return {"words": []}
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            backup = DATA_FILE.with_suffix(f".json.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            DATA_FILE.rename(backup)
            save_words({"words": []})
            return {"words": []}


def save_words(data: dict) -> None:
    """原子写入：先写临时文件再替换，防止并发写丢数据和写入中断损坏"""
    with _write_lock:
        tmp = DATA_FILE.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(DATA_FILE)


def now_iso() -> str:
    return datetime.now(CHINA_TZ).isoformat()


async def enrich_word(word: str) -> tuple[str, str, str]:
    """调用配置好的 Provider 补充音标、释义和例句，返回 (phonetic, definition, example)。失败返回空串。"""
    import logging
    logger = logging.getLogger("uvicorn")

    prompt = (
        f'For the English word "{word}", provide:\n'
        f'1. IPA phonetic transcription\n'
        f'2. Chinese definitions with parts of speech. '
        f'Use abbreviations: vt. 及物动词, vi. 不及物动词, n. 名词, adj. 形容词, '
        f'adv. 副词, prep. 介词, conj. 连词, pron. 代词.\n'
        f'IMPORTANT: synonyms of the same POS belong on ONE line, separated by a Chinese comma (，). '
        f'Only start a new line when switching to a different POS. '
        f'Every line MUST begin with a POS abbreviation.\n'
        f'Example: "n. 标准，规范，准则\\nvt. 使标准化，校准\\nadj. 标准的"\n'
        f'3. One natural example sentence\n'
        f'Reply ONLY with a JSON object, no other text:\n'
        f'{{"phonetic": "/.../", "definition": "n. 释义一，释义二\\nvt. 及物释义", "example": "..."}}'
    )
    try:
        if config.get_provider() == "ollama":
            ollama_cfg = config.get_ollama_config()
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(ollama_cfg["url"], json={
                    "model": ollama_cfg["model"],
                    "prompt": prompt,
                    "stream": False,
                })
                resp.raise_for_status()
                text = resp.json()["response"].strip()
        elif config.get_provider() == "deepseek":
            ds_cfg = config.get_deepseek_config()
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    "https://api.deepseek.com/chat/completions",
                    json={
                        "model": ds_cfg["model"],
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                    },
                    headers={"Authorization": f"Bearer {ds_cfg['api_key']}"},
                )
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"].strip()

        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if not match:
            logger.warning(f"[enrich] {word} — 响应中未找到 JSON 对象：{text[:200]}")
            return "", "", ""
        data = json.loads(match.group())
        return (
            data.get("phonetic", ""),
            data.get("definition", ""),
            data.get("example", ""),
        )
    except Exception as e:
        logger.warning(f"[enrich] {word} — 请求失败：{type(e).__name__}: {e}")
        return "", "", ""


# ─── API: SSE 事件流 ──────────────────────────────────────

@app.get("/api/events")
async def event_stream(request: Request):
    """SSE 端点 — 推送 enrichment 完成事件"""

    async def generate():
        if _event_queue is None:
            return
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(_event_queue.get(), timeout=15)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── API: 健康检查 ────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """检测当前配置的 Provider 是否可达"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            if config.get_provider() == "ollama":
                ollama_cfg = config.get_ollama_config()
                # Ollama API: 用 /api/tags 检测
                url = ollama_cfg["url"].replace("/api/generate", "/api/tags")
                resp = await client.get(url)
                if resp.is_success:
                    return {"provider": "ollama", "status": "connected"}
            elif config.get_provider() == "deepseek":
                ds_cfg = config.get_deepseek_config()
                resp = await client.post(
                    "https://api.deepseek.com/chat/completions",
                    json={"model": ds_cfg["model"], "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
                    headers={"Authorization": f"Bearer {ds_cfg['api_key']}"},
                )
                if resp.is_success:
                    return {"provider": "deepseek", "status": "connected"}
    except Exception:
        pass
    return {"provider": config.get_provider(), "status": "disconnected"}


# ─── API: 单词 CRUD ───────────────────────────────────────

@app.get("/api/words")
def list_words(
    q: str = Query(default=""),
    date: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=10000),
):
    data = load_words()
    words = _filter_words(data, q, date)

    total = len(words)
    start = (page - 1) * size
    page_words = words[start : start + size]

    return {
        "words": page_words,
        "total": total,
        "page": page,
        "size": size,
        "pages": max((total + size - 1) // size, 1),
    }


@app.get("/api/dates")
def list_dates():
    data = load_words()
    dates = sorted({
        w["created_at"][:10]
        for w in data["words"]
        if "created_at" in w
    }, reverse=True)
    return {"dates": dates}


# 注意：/api/words/export 和 /api/words/enrich-missing 路由必须在
# /api/words/{word_id} 之前，否则会被当成 word_id 匹配。
@app.get("/api/words/export")
def export_words(
    format: str = Query(default="json"),
    q: str = Query(default=""),
    date: str = Query(default=""),
):
    data = load_words()
    words = _filter_words(data, q, date)
    today = datetime.now(CHINA_TZ).strftime("%Y-%m-%d")

    if format == "csv":
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["单词", "音标", "释义", "例句", "日期"])
        for item in words:
            w.writerow([item["word"], item["phonetic"], item["definition"], item["example"], item["created_at"][:10]])
        out.seek(0)
        return StreamingResponse(
            iter([out.getvalue()]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=vocabulary-{today}.csv"},
        )

    if format == "pdf":
        use_cjk = _CJK_FONT_PATH is not None

        # ── 构建 PDF ──────────────────────────────────
        class _VocabPDF(FPDF):
            def __init__(self):
                super().__init__("P", "mm", "A4")
                self._cjk = use_cjk
                if use_cjk:
                    self.add_font("CJK", "", _CJK_FONT_PATH)

            def header(self):
                fnt = "CJK" if self._cjk else "Helvetica"
                txt = "词汇笔记本 · 导出" if self._cjk else "Vocabulary Notebook · Export"
                self.set_font(fnt, "", 9)
                self.set_text_color(136, 136, 136)
                self.cell(0, 10, txt, align="C")
                self.ln(12)

            def footer(self):
                fnt = "CJK" if self._cjk else "Helvetica"
                txt = f"第 {self.page_no()} 页" if self._cjk else f"Page {self.page_no()}"
                self.set_y(-20)
                self.set_font(fnt, "", 8)
                self.set_text_color(170, 170, 170)
                self.cell(0, 10, txt, align="C")

        pdf = _VocabPDF()
        pdf.set_auto_page_break(True, 22)
        pdf.set_left_margin(22)
        pdf.set_right_margin(22)
        pdf.set_top_margin(22)

        body_font = "CJK" if use_cjk else "Helvetica"

        pdf.add_page()

        # 日期行
        date_font = "CJK" if use_cjk else "Helvetica"
        date_text = f"导出日期：{today} · 共 {len(words)} 个单词" if use_cjk else f"Export Date: {today} · {len(words)} words"
        pdf.set_font(date_font, "", 9)
        pdf.set_text_color(153, 153, 153)
        pdf.cell(0, 8, date_text, align="R")
        pdf.ln(16)

        for item in words:
            # 检查卡片空间（估算约 45mm）
            if pdf.get_y() > pdf.h - pdf.b_margin - 45:
                pdf.add_page()

            # ── 单词 + 音标 ──
            word_text = html_mod.unescape(item["word"])
            phonetic = html_mod.unescape(item.get("phonetic", ""))
            pdf.set_font(body_font, "", 16)
            pdf.set_text_color(26, 26, 26)
            pdf.cell(0, 8, word_text)
            pdf.ln(9)
            if phonetic:
                pdf.set_font(body_font, "", 11)
                pdf.set_text_color(102, 102, 102)
                pdf.cell(0, 6, phonetic)
                pdf.ln(8)

            # ── 释义 ──
            pdf.set_x(pdf.l_margin)
            pdf.set_font(body_font, "", 12)
            pdf.set_text_color(51, 51, 51)
            pdf.multi_cell(0, 7, html_mod.unescape(item["definition"]))

            # ── 例句 ──
            example = html_mod.unescape(item.get("example", ""))
            if example:
                pdf.set_x(pdf.l_margin)
                pdf.set_font(body_font, "", 11)
                pdf.set_text_color(85, 85, 85)
                pdf.multi_cell(0, 6, f'"{example}"')

            # ── 分隔线 ──
            pdf.set_draw_color(221, 221, 221)
            y = pdf.get_y() + 2
            pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
            pdf.set_y(y + 5)

        pdf_bytes = pdf.output()
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=vocabulary-{today}.pdf"},
        )

    # 默认 JSON
    out = io.StringIO()
    json.dump({"words": words, "exported_at": now_iso()}, out, ensure_ascii=False, indent=2)
    out.seek(0)
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=vocabulary-{today}.json"},
    )


@app.post("/api/words/enrich-missing")
async def enrich_missing():
    """扫描缺失 definition 的单词，跳过冷却期内已完成/进行中的。"""
    now = asyncio.get_event_loop().time()
    data = load_words()
    missing = [
        w for w in data["words"]
        if not w.get("definition", "").strip()
        and _enriching_ids.get(w["id"], 0) + _ENRICH_COOLDOWN < now
    ]
    if not missing:
        in_cooldown = sum(
            1 for w in data["words"]
            if not w.get("definition", "").strip()
            and _enriching_ids.get(w["id"], 0) + _ENRICH_COOLDOWN >= now
        )
        msg = f"没有需要补全的单词" if not in_cooldown else f"{in_cooldown} 个单词正在补全中或刚尝试过，请稍后"
        return {"enriched": 0, "message": msg}

    for w in missing:
        _enriching_ids[w["id"]] = now
        await _enrich_queue.put((w["id"], w["word"]))

    return {
        "enriched": len(missing),
        "word_ids": [w["id"] for w in missing],
        "message": f"已加入 {len(missing)} 个单词到补全队列，逐个处理中",
    }


@app.get("/api/words/{word_id}")
def get_word(word_id: str):
    data = load_words()
    for w in data["words"]:
        if w["id"] == word_id:
            return {"word": w}
    raise HTTPException(status_code=404, detail="单词不存在")


@app.post("/api/words")
async def create_word(body: dict):
    word_text = body.get("word", "").strip()
    if not word_text:
        raise HTTPException(status_code=422, detail="单词不能为空")

    data = load_words()
    word_lower = word_text.lower()

    # 重复检测：同单词已存在时返回 409，附上已有记录供前端提示
    for w in data["words"]:
        if w["word"].lower() == word_lower:
            raise HTTPException(
                status_code=409,
                detail=f"「{w['word']}」已存在",
            )

    word_id = uuid.uuid4().hex[:12]
    word_obj = {
        "id": word_id,
        "word": word_text,
        "definition": body.get("definition", "").strip(),
        "phonetic": "",
        "example": "",
        "created_at": now_iso(),
    }

    data["words"].append(word_obj)
    save_words(data)

    # 送入补全队列，后台串行处理
    _enriching_ids[word_id] = asyncio.get_event_loop().time()
    await _enrich_queue.put((word_id, word_text))

    return {"word": word_obj}


async def _enrich_worker():
    """单 worker 从队列串行取任务，逐个调用 Ollama，避免并发排队超时"""
    while True:
        word_id, word_text = await _enrich_queue.get()
        try:
            phonetic, definition, example = await enrich_word(word_text)
            if not phonetic and not definition and not example:
                # 失败保留 _enriching_ids 中的时间戳，冷却期内不会重试
                continue

            with _write_lock:
                data = load_words()
                for w in data["words"]:
                    if w["id"] == word_id:
                        if phonetic:
                            w["phonetic"] = phonetic
                        if definition:
                            w["definition"] = definition
                        if example:
                            w["example"] = example
                        save_words(data)
                        break

            if _event_queue is not None:
                await _event_queue.put({
                    "type": "enriched",
                    "word_id": word_id,
                    "phonetic": phonetic,
                    "definition": definition,
                    "example": example,
                })
        finally:
            _enrich_queue.task_done()


@app.put("/api/words/{word_id}")
def update_word(word_id: str, body: dict):
    data = load_words()
    for w in data["words"]:
        if w["id"] == word_id:
            if "word" in body:
                w["word"] = body["word"].strip()
            if "definition" in body:
                w["definition"] = body["definition"].strip()
            save_words(data)
            return {"word": w}
    raise HTTPException(status_code=404, detail="单词不存在")


@app.delete("/api/words/{word_id}")
def delete_word(word_id: str):
    data = load_words()
    before = len(data["words"])
    data["words"] = [w for w in data["words"] if w["id"] != word_id]
    if len(data["words"]) == before:
        raise HTTPException(status_code=404, detail="单词不存在")
    save_words(data)
    return {"ok": True}


# ─── 导出辅助函数 ─────────────────────────────────────────

def _filter_words(data: dict, q: str, date: str) -> list:
    words = data["words"]
    if date:
        words = [w for w in words if w["created_at"].startswith(date)]
    if q:
        ql = q.lower()
        words = [w for w in words if ql in w["word"].lower() or ql in w["definition"].lower()]
    return words


# ─── 静态文件（生产模式）──────────────────────────────────
# 静态资源挂载必须在 catch-all 路由之前，否则 /assets/* 会被当 SPA 路由吞掉

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


@app.get("/")
async def serve_spa():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(
            status_code=404,
            detail="前端未构建。请运行: cd frontend && npm run build",
        )
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/{full_path:path}")
async def serve_spa_fallback(full_path: str):
    """所有非 API/非静态资源路径回退到 SPA，支持浏览器刷新和直接导航"""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="前端未构建")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


# ─── 网络工具 ─────────────────────────────────────────────

def get_lan_ip() -> str:
    """获取本机局域网 IP"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return ""


# ─── 启动入口 ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    host = "0.0.0.0"
    port = 1400
    lan_ip = get_lan_ip()

    print("═" * 52)
    print("  词汇笔记本  Vocabulary Notebook")
    print("═" * 52)
    print(f"  本地访问  →  http://localhost:{port}")
    if lan_ip:
        print(f"  局域网    →  http://{lan_ip}:{port}")
    print("═" * 52)
    print()

    uvicorn.run(app, host=host, port=port, log_level="warning")
