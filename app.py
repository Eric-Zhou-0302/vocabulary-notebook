"""词汇笔记本 — FastAPI 后端"""
import asyncio
import csv
import html as html_mod
import io
import math
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
    backup_task = asyncio.create_task(_periodic_backup_loop())
    yield
    backup_task.cancel()
    worker_task.cancel()
    for t in (backup_task, worker_task):
        try:
            await t
        except asyncio.CancelledError:
            pass


async def _periodic_backup_loop():
    """每 10 分钟把 words.json 原子复制到 words.json.bak。

    设计意图：这是 T18 期间数据被无痕覆盖的事后兜底 — 万一主文件被误删 / 损坏 /
    被代码错误重写，备份至少落后 ≤10 分钟。原子写（tmp+rename）保证备份本身不被中途
    写入中断。空数据跳过（避免把已丢的 0 词状态覆盖掉还能救的旧备份）。
    """
    while True:
        try:
            await asyncio.sleep(BACKUP_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            return
        try:
            if not DATA_FILE.exists():
                continue
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            if len(data.get("words", [])) < 1:
                # 跳过空数据，不让"丢失"状态覆盖掉能救的旧备份
                continue
            backup = DATA_FILE.with_suffix(".json.bak")
            tmp = DATA_FILE.with_suffix(".json.bak.tmp")
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(backup)
            print(f"  [backup] words.json → words.json.bak ({len(data['words'])} words)")
        except asyncio.CancelledError:
            return
        except Exception as e:
            # 备份失败不能拖垮服务
            print(f"  [backup] failed: {type(e).__name__}: {e}")


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
# 进度追踪
_enrich_current: Optional[str] = None
_enrich_batch_total: int = 0
_enrich_batch_done: int = 0

# ─── 周期备份 ────────────────────────────────────────────
# 后端运行时每 10 分钟把 words.json 原子复制到 words.json.bak。
# 万一主文件被误删/损坏/被代码错误重写，备份至少落后 ≤10 分钟。
BACKUP_INTERVAL_SECONDS = 600  # 10 分钟


# ─── PDF 字体路径 (fpdf2 纯 Python，零系统依赖) ──────────

_CJK_FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
if not os.path.exists(_CJK_FONT_PATH):
    _CJK_FONT_PATH = None  # 兜底：中文显示为空白，但不会崩溃


# ─── PDF 表格化导出 ─────────────────────────────────────

def _estimate_lines(text: str, col_w_mm: float, font_size_pt: float) -> int:
    """估算文本在指定列宽（mm）和字号（pt）下需要多少行。

    启发式：CJK 字符 ≈ 1em，全角标点 ≈ 0.85em，
    ASCII 字母 ≈ 0.5em，数字 / 半角标点 ≈ 0.55em。
    """
    if not text:
        return 0
    em = font_size_pt * 0.3528  # pt → mm
    total_lines = 0
    for para in text.split("\n"):
        w = 0.0
        for ch in para:
            cp = ord(ch)
            if 0x2E80 <= cp <= 0x303E or 0x3400 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF:
                w += em * 1.0  # CJK / 全角
            elif 0xFF00 <= cp <= 0xFFEF:
                w += em * 0.85  # 全角标点
            elif ch.isascii() and ch.isalpha():
                w += em * 0.50  # Latin
            else:
                w += em * 0.55  # 数字 / 半角标点 / 其他
        total_lines += max(1, math.ceil(w / col_w_mm))
    return total_lines


def _build_pdf(words: list[dict], today: str, use_cjk: bool, cjk_font_path: Optional[str]) -> bytes:
    """渲染词汇笔记本 PDF：密集表格布局，~20 词/页。

    设计: Scholar's Compact
    - 顶栏: 标题 + 日期 + 计数 + 双线分割
    - 表头: 序号 / 单词 + 音标 / 释义 / 例句
    - 行: 斑马纹（极淡米色），超细分隔线
    - 字: 单词 Times Bold, 音标 Courier Italic, 释义 Helvetica, 例句 Italic
    - 底栏: 页码 + 总数
    """

    # ── 字体注册 ──
    class _VocabPDF(FPDF):
        def __init__(self):
            super().__init__("P", "mm", "A4")
            self._cjk = use_cjk
            self._word_count = len(words)
            if use_cjk:
                self.add_font("CJK", "", cjk_font_path)
                self.add_font("CJK", "B", cjk_font_path)
                self.add_font("CJK", "I", cjk_font_path)

    pdf = _VocabPDF()

    # ── 排版常量 ──
    M_L, M_R, M_T, M_B = 16, 16, 14, 16
    pdf.set_margins(M_L, M_T, M_R)
    pdf.set_auto_page_break(False)  # 手动控制分页
    pdf.set_left_margin(M_L)
    pdf.set_right_margin(M_R)
    pdf.set_top_margin(M_T)
    pdf.set_auto_page_break(False)

    PAGE_W = pdf.w  # 210
    CONTENT_W = PAGE_W - M_L - M_R  # 178

    # 列宽（mm）
    COL_NUM_W = 8
    COL_WORD_W = 36
    COL_DEF_W = 86
    COL_EX_W = CONTENT_W - COL_NUM_W - COL_WORD_W - COL_DEF_W  # 48

    COL_X = {
        "num": M_L,
        "word": M_L + COL_NUM_W,
        "def": M_L + COL_NUM_W + COL_WORD_W,
        "ex": M_L + COL_NUM_W + COL_WORD_W + COL_DEF_W,
    }

    # 行高常量
    LH_DEF = 8.5 * 0.3528 * 1.22  # 8.5pt × 1.22 leading ≈ 3.66mm
    LH_EX = 7.5 * 0.3528 * 1.22   # 7.5pt × 1.22 leading ≈ 3.23mm
    ROW_PAD_TOP = 1.6
    ROW_PAD_BOT = 1.4
    MIN_ROW_H = 8.8

    # 顶栏 + 表头占用高度
    HEADER_BAND_H = 11
    HEADER_RULE_GAP = 1.2
    COL_HEADER_H = 6.2
    COL_HEADER_GAP = 1.0
    TABLE_TOP_OFFSET = HEADER_BAND_H + HEADER_RULE_GAP + COL_HEADER_H + COL_HEADER_GAP
    TABLE_BOTTOM = pdf.h - M_B  # 281

    # ── 配色 ──
    C_TITLE = (38, 38, 38)
    C_META = (120, 116, 108)
    C_RULE = (180, 172, 156)        # 主分割线
    C_RULE_LITE = (215, 210, 196)   # 行间细线
    C_ZEBRA = (247, 243, 232)       # 斑马米色
    C_NUM = (170, 162, 142)         # 序号灰
    C_WORD = (20, 20, 20)
    C_PHON = (130, 130, 130)
    C_DEF = (60, 60, 60)
    C_EX = (110, 110, 110)
    C_HEADER_BG = (50, 46, 40)      # 表头深色背景
    C_HEADER_FG = (245, 240, 228)

    sans = "CJK" if use_cjk else "Helvetica"
    serif = "CJK" if use_cjk else "Times"
    mono = "CJK" if use_cjk else "Courier"

    # ── 头部 ──
    def draw_header():
        y = M_T
        # 标题行
        pdf.set_xy(M_L, y)
        pdf.set_font(serif, "B", 14)
        pdf.set_text_color(*C_TITLE)
        title = "VOCABULARY NOTEBOOK"
        pdf.cell(80, 6.5, title)
        # 副标题（中文）
        if use_cjk:
            pdf.set_xy(M_L, y + 6.5)
            pdf.set_font(sans, "", 8.5)
            pdf.set_text_color(*C_META)
            pdf.cell(80, 4, "词 汇 笔 记 本 · 导 出")
        # 元信息右对齐
        pdf.set_xy(M_L, y)
        pdf.set_font(mono, "", 8)
        pdf.set_text_color(*C_META)
        meta = f"{today}  ·  {len(words):>4} WORDS"
        pdf.cell(CONTENT_W, 6.5, meta, align="R")
        if use_cjk:
            pdf.set_xy(M_L, y + 6.5)
            pdf.set_font(sans, "", 7.5)
            pdf.cell(CONTENT_W, 4, f"导出日期 {today}    共 {len(words)} 个单词", align="R")
        # 双线分割
        pdf.set_draw_color(*C_RULE)
        pdf.set_line_width(0.4)
        pdf.line(M_L, M_T + HEADER_BAND_H, M_L + CONTENT_W, M_T + HEADER_BAND_H)
        pdf.set_line_width(0.15)
        pdf.line(M_L, M_T + HEADER_BAND_H + 1.2, M_L + CONTENT_W, M_T + HEADER_BAND_H + 1.2)

    # ── 表头 ──
    def draw_col_header(y: float):
        h = COL_HEADER_H
        pdf.set_fill_color(*C_HEADER_BG)
        pdf.rect(M_L, y, CONTENT_W, h, style="F")
        pdf.set_font(sans if use_cjk else "Helvetica", "B", 8.5)
        pdf.set_text_color(*C_HEADER_FG)
        labels = [
            ("#",       COL_X["num"], COL_NUM_W, "C"),
            ("WORD",    COL_X["word"], COL_WORD_W, "L"),
            ("DEFINITION", COL_X["def"], COL_DEF_W, "L"),
            ("EXAMPLE", COL_X["ex"], COL_EX_W, "L"),
        ]
        for txt, x, w, align in labels:
            pdf.set_xy(x + 2, y + 1.6)
            pdf.cell(w - 4, h - 1.6, txt, align=align)
        return y + h

    # ── 表头后 ──
    def draw_table_separator(y: float):
        pdf.set_draw_color(*C_RULE_LITE)
        pdf.set_line_width(0.15)
        pdf.line(M_L, y, M_L + CONTENT_W, y)
        return y

    # ── 单行 ──
    def draw_row(idx: int, item: dict, y: float, zebra: bool):
        word = html_mod.unescape(item.get("word", "")).strip()
        phonetic = html_mod.unescape(item.get("phonetic", "")).strip()
        definition = html_mod.unescape(item.get("definition", "")).strip()
        example = html_mod.unescape(item.get("example", "")).strip()

        n_def = _estimate_lines(definition, COL_DEF_W - 4, 8.5)
        n_ex = _estimate_lines(example, COL_EX_W - 4, 7.5)
        text_h = n_def * LH_DEF + (n_ex * LH_EX + 1.0 if example else 0)
        row_h = max(MIN_ROW_H, ROW_PAD_TOP + text_h + ROW_PAD_BOT)

        # 斑马背景
        if zebra:
            pdf.set_fill_color(*C_ZEBRA)
            pdf.rect(M_L, y, CONTENT_W, row_h, style="F")

        # 序号（垂直居中）
        pdf.set_font(serif, "B", 8.5)
        pdf.set_text_color(*C_NUM)
        num_h = 4.0
        pdf.set_xy(COL_X["num"], y + (row_h - num_h) / 2)
        pdf.cell(COL_NUM_W, num_h, f"{idx:>3}", align="C")

        # 单词
        pdf.set_xy(COL_X["word"] + 1.5, y + ROW_PAD_TOP)
        pdf.set_font(serif, "B", 10.5)
        pdf.set_text_color(*C_WORD)
        pdf.cell(COL_WORD_W - 3, 4.4, word)
        # 音标
        if phonetic:
            pdf.set_xy(COL_X["word"] + 1.5, y + ROW_PAD_TOP + 4.2)
            pdf.set_font(mono, "I", 7)
            pdf.set_text_color(*C_PHON)
            pdf.cell(COL_WORD_W - 3, 3.2, phonetic)

        # 释义
        pdf.set_xy(COL_X["def"] + 1.5, y + ROW_PAD_TOP)
        pdf.set_font(sans, "", 8.5)
        pdf.set_text_color(*C_DEF)
        lines_def = _wrap_lines(definition, COL_DEF_W - 3, 8.5)
        cy = y + ROW_PAD_TOP
        for ln in lines_def[:max(1, n_def)]:
            pdf.set_xy(COL_X["def"] + 1.5, cy)
            pdf.cell(COL_DEF_W - 3, LH_DEF, ln)
            cy += LH_DEF

        # 例句（缩进 + 斜体）
        if example and n_ex > 0:
            cy += 0.5
            ex_text = f'“{example}”'
            lines_ex = _wrap_lines(ex_text, COL_EX_W - 3, 7.5)
            pdf.set_font(sans, "I", 7.5)
            pdf.set_text_color(*C_EX)
            for ln in lines_ex[:max(1, n_ex)]:
                pdf.set_xy(COL_X["ex"] + 1.5, cy)
                pdf.cell(COL_EX_W - 3, LH_EX, ln)
                cy += LH_EX

        # 行底分割线
        pdf.set_draw_color(*C_RULE_LITE)
        pdf.set_line_width(0.12)
        pdf.line(M_L, y + row_h, M_L + CONTENT_W, y + row_h)
        pdf.set_line_width(0.15)

        return y + row_h

    # ── 文本换行（基于宽度估算） ──
    def _wrap_lines(text: str, max_w_mm: float, font_size_pt: float) -> list[str]:
        """按列宽把文本切成行。CJK 字符可断，Latin 按词断。"""
        if not text:
            return [""]
        em = font_size_pt * 0.3528
        out: list[str] = []
        for para in text.split("\n"):
            cur = ""
            cur_w = 0.0
            # 按字符遍历，CJK 单字断、Latin 按空格切词
            i = 0
            tokens: list[str] = []
            buf = ""
            for ch in para:
                cp = ord(ch)
                if 0x2E80 <= cp <= 0x303E or 0x3400 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF:
                    if buf:
                        tokens.append(buf)
                        buf = ""
                    tokens.append(ch)  # CJK 单字 token
                elif ch == " ":
                    if buf:
                        tokens.append(buf)
                        buf = ""
                    tokens.append(" ")
                else:
                    buf += ch
            if buf:
                tokens.append(buf)

            for tk in tokens:
                w = 0.0
                for ch in tk:
                    cp = ord(ch)
                    if 0x2E80 <= cp <= 0x303E or 0x3400 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF:
                        w += em * 1.0
                    elif 0xFF00 <= cp <= 0xFFEF:
                        w += em * 0.85
                    elif ch.isascii() and ch.isalpha():
                        w += em * 0.5
                    else:
                        w += em * 0.55
                if cur_w + w <= max_w_mm or not cur:
                    cur += tk
                    cur_w += w
                else:
                    out.append(cur.rstrip())
                    cur = tk.lstrip() if tk != " " else ""
                    cur_w = w if tk != " " else 0
            if cur:
                out.append(cur.rstrip())
        return out

    # ── 页脚 ──
    def draw_footer():
        pdf.set_xy(M_L, pdf.h - M_B + 4)
        pdf.set_font(sans if use_cjk else "Helvetica", "", 7.5)
        pdf.set_text_color(*C_META)
        left = "Vocab Notebook"
        right = f"{pdf.page_no()} / {pdf.pages_count}"
        pdf.cell(CONTENT_W / 2, 4, left)
        pdf.cell(CONTENT_W / 2, 4, right, align="R")
        # 细线
        pdf.set_draw_color(*C_RULE_LITE)
        pdf.set_line_width(0.15)
        pdf.line(M_L, pdf.h - M_B + 3, M_L + CONTENT_W, pdf.h - M_B + 3)

    # ── 渲染循环 ──
    pdf.add_page()
    draw_header()
    y = M_T + TABLE_TOP_OFFSET
    draw_table_separator(y - 0.5)
    y = draw_col_header(y - 0.5)

    for idx, item in enumerate(words, 1):
        # 预估算行高，检查是否放得下
        definition = html_mod.unescape(item.get("definition", ""))
        example = html_mod.unescape(item.get("example", ""))
        n_def_est = _estimate_lines(definition, COL_DEF_W - 4, 8.5)
        n_ex_est = _estimate_lines(example, COL_EX_W - 4, 7.5)
        text_h_est = n_def_est * LH_DEF + (n_ex_est * LH_EX + 1.0 if example else 0)
        row_h_est = max(MIN_ROW_H, ROW_PAD_TOP + text_h_est + ROW_PAD_BOT)

        # 放不下则分页
        if y + row_h_est > TABLE_BOTTOM:
            draw_footer()
            pdf.add_page()
            draw_header()
            y = M_T + TABLE_TOP_OFFSET
            draw_table_separator(y - 0.5)
            y = draw_col_header(y - 0.5)

        y = draw_row(idx, item, y, zebra=(idx % 2 == 0))

    draw_footer()

    return bytes(pdf.output())


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

    prompt = f'''For the English word "{word}", provide its dictionary
headword's phonetic, definition, and an English example.

CRITICAL — determine the canonical headword first:
- "{word}" may be a plural, past tense, or derived form.
  Identify the base headword, then return ITS definitions.
- Exception: if "{word}" is itself an established headword
  (e.g., standalone noun like "running", "swimming", "meeting",
  "building", "writing", "cooking", "feeling"), keep it.
- Do not invent senses for "{word}" that are not in major
  English dictionaries.
- "{word}" may only be an adjective — do not add a noun/verb
  sense that doesn't exist (e.g., "intricate" is adj only).

CRITICAL — handle unrecognized words honestly:
- If "{word}" is a single word not in standard English
  dictionaries (typo, nonsense, abbreviation you're unsure
  of), return an empty JSON:
  {{"phonetic":"", "definition":"", "example":""}}
  Do NOT fabricate definitions for words you don't recognize.
- If "{word}" is a multi-word phrase (contains a space), it
  is a legitimate entry — treat it as a valid headword and
  return its phrase meaning (e.g., "in advance of", "take
  no notice of", "bottle stoppers"). Do NOT refuse phrases.
- For proper nouns, brand names, or technical jargon you're
  not certain about, also return empty JSON. Better to leave
  a word empty than to invent a fake meaning.
- When uncertain about any field, leave that field empty
  rather than guessing.

Examples:
  "granules"  → headword "granule" (n.)
  "esteemed"  → headword "esteem" (vt. / n.)
  "running"   → headword "running" (n.)
  "amassing"  → headword "amass" (vt.)
  "converged" → headword "converge" (vi.)

The example sentence MUST be in English (not Chinese), short,
and illustrate one of the senses above.

Use POS abbreviations: vt. vi. n. adj. adv. prep. conj. pron.
Synonyms of the same POS belong on ONE line, separated by
Chinese comma (，). Every line MUST start with a POS abbreviation.

Reply ONLY with a JSON object, no other text:
{{"phonetic": "/.../", "definition": "n. 释义一，释义二\\nvt. 及物释义", "example": "..."}}'''
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
    sort: str = Query(default=""),
    letter: str = Query(default=""),
):
    data = load_words()
    # 先按 q+date+sort 过滤一次，用于计算 available_letters（不含 letter 自身的影响）
    pre_letter = _filter_words(data, q, date, sort)
    available_letters = sorted({
        w["word"][0].lower() for w in pre_letter if w.get("word")
    })

    words = _filter_words(data, q, date, sort, letter)

    total = len(words)
    start = (page - 1) * size
    page_words = words[start : start + size]

    return {
        "words": page_words,
        "total": total,
        "page": page,
        "size": size,
        "pages": max((total + size - 1) // size, 1),
        "available_letters": available_letters,
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
    sort: str = Query(default=""),
):
    data = load_words()
    words = _filter_words(data, q, date, sort)
    today = datetime.now(CHINA_TZ).strftime("%Y-%m-%d")

    if format == "csv":
        out = io.StringIO()
        out.write("﻿")  # UTF-8 BOM — Excel 看这个知道是 UTF-8,不会按 GBK 误读
        w = csv.writer(out)
        w.writerow(["单词", "音标", "释义", "例句", "日期"])
        for item in words:
            w.writerow([item["word"], item["phonetic"], item["definition"], item["example"], item["created_at"][:10]])
        out.seek(0)
        return StreamingResponse(
            iter([out.getvalue().encode("utf-8")]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=vocabulary-{today}.csv"},
        )

    if format == "pdf":
        use_cjk = _CJK_FONT_PATH is not None
        pdf_bytes = _build_pdf(words, today, use_cjk, _CJK_FONT_PATH)
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


async def _enqueue_enrich_batch(items: list) -> None:
    """送入 enrich 队列并累加 batch 计数器。

    仅做"入队 + 累加"，不做重置。重置由调用方在合适的时机显式调用
    `_maybe_reset_batch_if_idle()`，这样 enrich-missing 即使在 0 missing 提前
    return 的路径上也能把上一批残留状态清掉。

    调用方必须在同一协程内连续调用（不要跨 await），这样检查 + 入队 + 计数的
    同步段不会被 worker 协程打断，竞态安全。
    """
    global _enrich_batch_total
    if not items:
        return
    now = asyncio.get_event_loop().time()
    for word_id, word_text in items:
        _enriching_ids[word_id] = now
        await _enrich_queue.put((word_id, word_text))
    _enrich_batch_total += len(items)


def _maybe_reset_batch_if_idle() -> None:
    """若 worker 空闲 + 队列空 + 上一批已结束，重置 batch 计数器。

    同步函数：调用方必须在 _enrich_queue.put 之前同一同步段内执行，竞态安全。
    """
    global _enrich_batch_total, _enrich_batch_done
    if not _enrich_current and _enrich_queue.qsize() == 0 and _enrich_batch_total > 0:
        _enrich_batch_total = 0
        _enrich_batch_done = 0


@app.post("/api/words/enrich-missing")
async def enrich_missing():
    """扫描缺失 definition 的单词，跳过冷却期内已完成/进行中的。"""
    # 入口处先尝试重置上一批残留状态 — 即使下面 0 missing 提前 return，
    # 也能让 batch_total/batch_done 清零，避免污染后续观察。
    _maybe_reset_batch_if_idle()
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

    await _enqueue_enrich_batch([(w["id"], w["word"]) for w in missing])

    return {
        "enriched": len(missing),
        "word_ids": [w["id"] for w in missing],
        "message": f"已加入 {len(missing)} 个单词到补全队列，逐个处理中",
    }


@app.get("/api/enrich/progress")
def enrich_progress():
    """返回当前 enrichment 队列进度"""
    queue_size = _enrich_queue.qsize() if _enrich_queue else 0
    data = load_words()
    total_missing = sum(
        1 for w in data["words"]
        if not w.get("definition", "").strip()
    )
    return {
        "queue_size": queue_size,
        "current_word": _enrich_current,
        "batch_total": _enrich_batch_total,
        "batch_done": _enrich_batch_done,
        "total_missing": total_missing,
        "is_processing": _enrich_current is not None,
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

    # 送入补全队列，后台串行处理（持续累加，不重置 — 用户显式补全缺失才是新一批）
    await _enqueue_enrich_batch([(word_id, word_text)])

    return {"word": word_obj}


async def _enrich_worker():
    """单 worker 从队列串行取任务，逐个调用 Ollama，避免并发排队超时"""
    global _enrich_current, _enrich_batch_done
    import logging
    logger = logging.getLogger("uvicorn")
    logger.warning("[enrich-worker] started")
    while True:
        word_id, word_text = await _enrich_queue.get()
        _enrich_current = word_text
        logger.warning(f"[enrich-worker] picked: {word_text!r} id={word_id}")
        try:
            phonetic, definition, example = await enrich_word(word_text)
            if not phonetic and not definition and not example:
                # 全空响应。词组(空格)静默不打扰 — 可能是 deepseek 对该词组不熟;
                # 单个词推 toast 提示 — 可能是拼错/不存在/网络失败。
                logger.warning(f"[enrich] {word_text} — deepseek 返回空")
                if " " not in word_text and _event_queue is not None:
                    await _event_queue.put({
                        "type": "enrich_failed",
                        "word_id": word_id,
                        "word": word_text,
                        "reason": "deepseek 未返回任何内容(可能是错误单词、不存在的词、或网络失败)",
                    })
                _enriching_ids.pop(word_id, None)
                continue

            # 后处理校验：拦截拼写错/中文例句/词性误标
            ok, reason = _enrich_post_check(word_text, phonetic, definition, example)
            if not ok:
                logger.warning(f"[enrich-check] {word_text} — 拒绝写回: {reason}")
                if _event_queue is not None:
                    await _event_queue.put({
                        "type": "enrich_failed",
                        "word_id": word_id,
                        "word": word_text,
                        "reason": reason,
                    })
                _enriching_ids.pop(word_id, None)
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

            _enrich_batch_done += 1
            if _event_queue is not None:
                await _event_queue.put({
                    "type": "enriched",
                    "word_id": word_id,
                    "phonetic": phonetic,
                    "definition": definition,
                    "example": example,
                })
        except Exception as e:
            # 外层保护:任何意外异常都不让 worker 死,记录后继续下一个
            logger.exception(f"[enrich-worker] UNCAUGHT EXCEPTION: {e}")
            import asyncio as _aio
            await _aio.sleep(1)
        finally:
            _enrich_current = None
            _enrich_queue.task_done()


def _enrich_post_check(word: str, phonetic: str, definition: str, example: str) -> tuple[bool, str]:
    """后处理校验 — 返回 (ok, reason)。

    三道闸:拼写(pyenchant) / 例句语种(langdetect) / 释义 POS 行头(纯正则)。
    任一失败 → 严格模式:不写回,清冷却,推 SSE enrich_failed 事件。
    库未装时优雅降级(log warning 后跳过该闸)。
    """
    import logging
    logger = logging.getLogger("uvicorn")

    # 1. 拼写 — 拦截 conffin/cublic/fivre/weav/undeter 这类
    # 词组(空格分隔)按分词查,避免 "bottle stoppers" 整串被误拒
    try:
        import enchant
        d = enchant.Dict("en_US")
        if " " in word:
            bad = [p for p in word.split() if not d.check(p)]
            if bad:
                return False, f"词组中分词拼写错 {bad}: {word!r}"
        else:
            if not d.check(word):
                return False, f"word 不在英语词典(疑似拼写错): {word!r}"
    except ImportError:
        pass  # pyenchant 未装 — 降级跳过
    except Exception as e:
        logger.warning(f"[enrich-check] {word} — 拼写检查异常: {type(e).__name__}: {e}")

    # 2. 例句含中文字符 → 拦截(algebra 中文例句这类)
    # 不做通用语种检测:langdetect 在 < 10 词的例句上误判率 30%+,
    # 会把短英文误判为 ro/af/so 等。直接看是否含中文更稳。
    if example and example.strip() and re.search(r"[一-鿿]", example):
        return False, f"例句包含中文字符: {example!r}"

    # 3. 释义每行以合法 POS 开头 — 拦截 divergent n. / intricate vt. / 冷门义项
    POS = {"vt.", "vi.", "n.", "adj.", "adv.", "prep.", "conj.", "pron."}
    for line in (definition or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if not any(line.startswith(p) for p in POS):
            return False, f"释义行不以 POS 开头: {line!r}"

    return True, ""


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

def _filter_words(data: dict, q: str, date: str, sort: str = "", letter: str = "") -> list:
    words = data["words"]
    if date:
        words = [w for w in words if w["created_at"].startswith(date)]
    if q:
        ql = q.lower()
        words = [w for w in words if ql in w["word"].lower() or ql in w["definition"].lower()]
    if letter:
        l = letter.lower()
        words = [w for w in words if w["word"].lower().startswith(l)]
    if sort == "alpha_asc":
        words = sorted(words, key=lambda w: w["word"].lower())
    elif sort == "alpha_desc":
        words = sorted(words, key=lambda w: w["word"].lower(), reverse=True)
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
