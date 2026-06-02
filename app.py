"""词汇笔记本 — FastAPI 后端"""
import csv
import io
import json
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from weasyprint import HTML

# ─── App ──────────────────────────────────────────────────

app = FastAPI(title="Vocabulary Notebook")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Config ───────────────────────────────────────────────

DATA_FILE = Path("words.json")
CHINA_TZ = timezone(timedelta(hours=8))
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma4:26b"
STATIC_DIR = Path("frontend/dist")
TEMPLATE_DIR = Path("templates")


def load_words() -> dict:
    """读取 words.json，不存在或损坏时返回空数据"""
    if not DATA_FILE.exists():
        save_words({"words": []})
        return {"words": []}
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        save_words({"words": []})
        return {"words": []}


def save_words(data: dict) -> None:
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def now_iso() -> str:
    return datetime.now(CHINA_TZ).isoformat()


async def enrich_word(word: str) -> tuple[str, str]:
    """调用 Ollama 补充音标和例句，返回 (phonetic, example)。失败返回空串。"""
    prompt = (
        f'For the English word "{word}", give its IPA phonetic transcription '
        f'and one natural example sentence.\n'
        f'Reply ONLY with a JSON object, no other text:\n'
        f'{{"phonetic": "/.../", "example": "..."}}'
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(OLLAMA_URL, json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
            })
            resp.raise_for_status()
            text = resp.json()["response"].strip()
            match = re.search(r"\{[^{}]*\}", text)
            if match:
                data = json.loads(match.group())
                return data.get("phonetic", ""), data.get("example", "")
    except Exception:
        pass
    return "", ""


# ─── API: 单词 CRUD ───────────────────────────────────────

@app.get("/api/words")
def list_words(
    q: str = Query(default=""),
    date: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
):
    data = load_words()
    words = data["words"]

    if date:
        words = [w for w in words if w["created_at"].startswith(date)]
    if q:
        ql = q.lower()
        words = [w for w in words if ql in w["word"].lower() or ql in w["definition"].lower()]

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
    dates = sorted({w["created_at"][:10] for w in data["words"]}, reverse=True)
    return {"dates": dates}


# 注意：/api/words/export 路由必须在 /api/words/{word_id} 之前，
# 否则 "export" 会被当成 word_id 匹配。
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
        template_path = TEMPLATE_DIR / "pdf_export.html"
        if not template_path.exists():
            raise HTTPException(status_code=500, detail="PDF 模板不存在")
        html = template_path.read_text(encoding="utf-8")

        cards = ""
        for item in words:
            phonetic_line = f'  <span class="phonetic">{item["phonetic"]}</span>' if item["phonetic"] else ""
            example_line = f'  <p class="example">"{item["example"]}"</p>' if item["example"] else ""
            cards += f"""<div class="card">
  <div class="word">{item["word"]}{phonetic_line}</div>
  <p class="definition">{item["definition"]}</p>
{example_line}</div>
"""
        html = html.replace("{{CARDS}}", cards)
        html = html.replace("{{DATE}}", today)
        html = html.replace("{{COUNT}}", str(len(words)))

        pdf_bytes = HTML(string=html).write_pdf()
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
    definition = body.get("definition", "").strip()
    if not word_text or not definition:
        raise HTTPException(status_code=422, detail="单词和释义不能为空")

    phonetic, example = await enrich_word(word_text)

    word_obj = {
        "id": uuid.uuid4().hex[:12],
        "word": word_text,
        "definition": definition,
        "phonetic": phonetic,
        "example": example,
        "created_at": now_iso(),
    }

    data = load_words()
    data["words"].append(word_obj)
    save_words(data)

    return {"word": word_obj, "enriched": bool(phonetic)}


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

@app.get("/")
async def serve_spa():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(
            status_code=404,
            detail="前端未构建。请运行: cd frontend && npm run build",
        )
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


# ─── 启动入口 ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
