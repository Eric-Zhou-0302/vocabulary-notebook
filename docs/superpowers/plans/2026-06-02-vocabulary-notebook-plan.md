# 词汇笔记本 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 Web 词汇管理应用——录入单词后自动补充音标/例句，支持浏览/闪卡/拼写测试三模式复习，可导出 JSON/CSV/PDF。

**Architecture:** FastAPI 后端提供 REST API，读写本地 JSON 文件，调用 Ollama 补充音标例句，WeasyPrint 生成 PDF。React SPA 前端通过 API 通信。生产模式 FastAPI 直接托管打包后的静态文件，单进程运行。

**Tech Stack:** Python 3 + FastAPI + httpx + WeasyPrint / React 18 + React Router 6 + Vite 5

---

## 文件结构

```
Vocabulary_ notebook/
├── .venv/                    # 创建：Python 虚拟环境
├── app.py                    # 创建：FastAPI 全部后端逻辑
├── requirements.txt          # 创建：Python 依赖
├── words.json                # 创建：运行时自动生成
├── templates/
│   └── pdf_export.html       # 创建：WeasyPrint PDF 模板
├── frontend/
│   ├── package.json          # 创建
│   ├── vite.config.js        # 创建
│   ├── index.html            # 创建
│   └── src/
│       ├── main.jsx          # 创建：React 入口
│       ├── App.jsx           # 创建：路由 + 布局
│       ├── App.css           # 创建：全局样式
│       ├── api.js            # 创建：API 请求封装
│       ├── pages/
│       │   ├── WordList.jsx  # 创建：单词列表页
│       │   ├── WordNew.jsx   # 创建：新增单词页
│       │   ├── WordDetail.jsx# 创建：单词详情页
│       │   └── Review.jsx    # 创建：复习页（三 Tab）
│       └── components/
│           ├── WordCard.jsx  # 创建：单词卡片
│           ├── Flashcard.jsx # 创建：闪卡组件
│           ├── SpellingTest.jsx # 创建：拼写测试组件
│           └── ExportMenu.jsx   # 创建：导出下拉菜单
```

---

### Task 1: Python 环境与依赖

**Files:**
- Create: `requirements.txt`
- Create: `.venv/` (via python3 -m venv)

- [ ] **Step 1: 创建 requirements.txt**

```txt
fastapi==0.115.6
uvicorn[standard]==0.34.0
httpx==0.28.1
weasyprint==63.1
```

- [ ] **Step 2: 创建虚拟环境并安装依赖**

```bash
cd "/Users/eric_zhou/Projects/Vocabulary_ notebook"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

验证: `pip list | grep -E "fastapi|uvicorn|httpx|weasyprint"` 应显示 4 个包。

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add Python dependencies"
```

---

### Task 2: Backend — FastAPI 完整实现

**Files:**
- Create: `app.py`

`app.py` 包含所有后端逻辑：JSON 读写、CRUD、Ollama 集成、导出（JSON/CSV/PDF）、静态文件托管。一次性写入。

- [ ] **Step 1: 创建 app.py**

```python
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
```

- [ ] **Step 2: 验证后端启动**

```bash
cd "/Users/eric_zhou/Projects/Vocabulary_ notebook"
source .venv/bin/activate
python app.py
```

访问 `http://localhost:8000/api/words`，应返回 `{"words":[],"total":0,"page":1,"size":20,"pages":1}`。

- [ ] **Step 3: 验证 CRUD（curl）**

```bash
# 新增单词（如果 Ollama 没运行，phonetic/example 会为空但单词仍然保存）
curl -s -X POST http://localhost:8000/api/words \
  -H "Content-Type: application/json" \
  -d '{"word":"ephemeral","definition":"短暂的"}' | python3 -m json.tool

# 列表
curl -s http://localhost:8000/api/words | python3 -m json.tool

# 搜索
curl -s "http://localhost:8000/api/words?q=eph" | python3 -m json.tool

# 详情（替换 ID）
curl -s http://localhost:8000/api/words/<id> | python3 -m json.tool

# 删除
curl -s -X DELETE http://localhost:8000/api/words/<id>
```

- [ ] **Step 4: Commit**

```bash
git add app.py words.json
git commit -m "feat: FastAPI backend with CRUD, Ollama enrichment, and export"
```

---

### Task 3: PDF 导出模板

**Files:**
- Create: `templates/pdf_export.html`

- [ ] **Step 1: 创建 templates/pdf_export.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  @page {
    size: A4;
    margin: 2cm 2.2cm;
    @top-center {
      content: "词汇笔记本 · 导出";
      font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
      font-size: 10pt;
      color: #888;
    }
    @bottom-center {
      content: "第 " counter(page) " 页";
      font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
      font-size: 9pt;
      color: #aaa;
    }
  }

  body {
    font-family: Georgia, "Times New Roman", serif;
    font-size: 12pt;
    line-height: 1.8;
    color: #222;
  }

  .date-line {
    text-align: right;
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 9pt;
    color: #999;
    margin-bottom: 1.5cm;
  }

  .card {
    break-inside: avoid;
    margin-bottom: 1.2cm;
    padding-bottom: 0.6cm;
    border-bottom: 0.5pt solid #ddd;
  }

  .word {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 16pt;
    font-weight: 700;
    color: #1a1a1a;
    margin-bottom: 2pt;
  }

  .phonetic {
    font-family: "Lucida Grande", "Helvetica Neue", Arial, sans-serif;
    font-size: 11pt;
    color: #666;
    font-weight: 400;
    margin-left: 0.5em;
  }

  .definition {
    font-size: 12pt;
    color: #333;
    margin: 6pt 0 4pt 0;
  }

  .example {
    font-family: Georgia, "Times New Roman", serif;
    font-size: 11pt;
    font-style: italic;
    color: #555;
    margin: 2pt 0 0 0;
  }
</style>
</head>
<body>
  <div class="date-line">导出日期：{{DATE}} · 共 {{COUNT}} 个单词</div>
  {{CARDS}}
</body>
</html>
```

- [ ] **Step 2: 验证 PDF 导出**

```bash
# 先确保至少有一个单词
curl -s -X POST http://localhost:8000/api/words \
  -H "Content-Type: application/json" \
  -d '{"word":"serendipity","definition":"意外发现美好事物的能力"}'

# 导出 PDF
curl -s -o /tmp/test.pdf "http://localhost:8000/api/words/export?format=pdf"
open /tmp/test.pdf
```

确认 PDF 排版正常、单词卡片不跨页。

- [ ] **Step 3: Commit**

```bash
git add templates/pdf_export.html
git commit -m "feat: PDF export template with WeasyPrint"
```

---

### Task 4: 前端工程搭建

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.jsx`

- [ ] **Step 1: 创建 frontend/package.json**

```json
{
  "name": "vocabulary-notebook",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.4",
    "vite": "^6.0.0"
  }
}
```

- [ ] **Step 2: 安装前端依赖**

```bash
cd "/Users/eric_zhou/Projects/Vocabulary_ notebook/frontend"
npm install
```

- [ ] **Step 3: 创建 frontend/vite.config.js**

```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

- [ ] **Step 4: 创建 frontend/index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>词汇笔记本</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.jsx"></script>
</body>
</html>
```

- [ ] **Step 5: 创建 frontend/src/main.jsx**

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './App.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
)
```

- [ ] **Step 6: 验证前端启动**

```bash
cd "/Users/eric_zhou/Projects/Vocabulary_ notebook/frontend"
npm run dev
```

打开 `http://localhost:5173`，应看到空白页面（尚无路由内容）。

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.js frontend/index.html frontend/src/main.jsx
git commit -m "chore: scaffold React + Vite frontend"
```

---

### Task 5: API Client + App Shell

**Files:**
- Create: `frontend/src/api.js`
- Create: `frontend/src/App.jsx`

- [ ] **Step 1: 创建 frontend/src/api.js**

```javascript
const BASE = '/api'

async function request(url, options = {}) {
  const res = await fetch(BASE + url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || '请求失败')
  }
  return res
}

export async function fetchWords({ q = '', date = '', page = 1, size = 20 } = {}) {
  const params = new URLSearchParams({ q, date, page, size })
  const res = await request(`/words?${params}`)
  return res.json()
}

export async function fetchDates() {
  const res = await request('/dates')
  return res.json()
}

export async function fetchWord(id) {
  const res = await request(`/words/${id}`)
  return res.json()
}

export async function createWord(word, definition) {
  const res = await request('/words', {
    method: 'POST',
    body: JSON.stringify({ word, definition }),
  })
  return res.json()
}

export async function updateWord(id, data) {
  const res = await request(`/words/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  return res.json()
}

export async function deleteWord(id) {
  await request(`/words/${id}`, { method: 'DELETE' })
}

export function exportUrl(format, { q = '', date = '' } = {}) {
  const params = new URLSearchParams({ format, q, date })
  return `${BASE}/words/export?${params}`
}
```

- [ ] **Step 2: 创建 frontend/src/App.jsx**

```jsx
import { Routes, Route, Link, useLocation } from 'react-router-dom'
import WordList from './pages/WordList'
import WordNew from './pages/WordNew'
import WordDetail from './pages/WordDetail'
import Review from './pages/Review'

export default function App() {
  const location = useLocation()

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">
          <Link to="/">词汇笔记本</Link>
        </h1>
        <nav className="app-nav">
          <Link to="/" className={location.pathname === '/' ? 'active' : ''}>
            单词列表
          </Link>
          <Link to="/word/new" className={location.pathname === '/word/new' ? 'active' : ''}>
            添加单词
          </Link>
          <Link to="/review" className={location.pathname === '/review' ? 'active' : ''}>
            复习
          </Link>
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<WordList />} />
          <Route path="/word/new" element={<WordNew />} />
          <Route path="/word/:id" element={<WordDetail />} />
          <Route path="/review" element={<Review />} />
        </Routes>
      </main>
    </div>
  )
}
```

- [ ] **Step 3: 验证路由**

打开 `http://localhost:5173`，应看到标题栏和导航链接。点击各链接验证路由切换。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api.js frontend/src/App.jsx
git commit -m "feat: API client and app shell with routing"
```

---

### Task 6: 全局样式

**Files:**
- Create: `frontend/src/App.css`

- [ ] **Step 1: 创建 frontend/src/App.css**

```css
/* ─── Reset & Base ─────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background: #f5f5f5;
  color: #222;
  line-height: 1.6;
}

a { color: inherit; text-decoration: none; }

/* ─── Layout ──────────────────────────── */
.app { max-width: 800px; margin: 0 auto; padding: 0 16px 40px; }

.app-header {
  display: flex; align-items: baseline; justify-content: space-between;
  padding: 20px 0 16px;
  border-bottom: 1px solid #e0e0e0;
  margin-bottom: 24px;
}

.app-title { font-size: 22px; font-weight: 700; }
.app-title a:hover { opacity: 0.7; }

.app-nav { display: flex; gap: 20px; font-size: 15px; }
.app-nav a { color: #666; padding-bottom: 2px; border-bottom: 2px solid transparent; }
.app-nav a:hover { color: #222; }
.app-nav a.active { color: #1a73e8; border-bottom-color: #1a73e8; }

.app-main { min-height: 60vh; }

/* ─── Cards ─────────────────────────────── */
.word-card {
  display: block; background: #fff; border-radius: 8px;
  padding: 16px 20px; margin-bottom: 10px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  transition: box-shadow 0.15s;
}
.word-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.12); }

.word-card .head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 4px; }
.word-card .word   { font-size: 18px; font-weight: 600; }
.word-card .phonetic { font-size: 13px; color: #888; }
.word-card .definition { font-size: 14px; color: #555; }

/* ─── Empty / Error ─────────────────────── */
.empty-state {
  text-align: center; padding: 60px 20px; color: #999;
}
.empty-state p { font-size: 16px; margin-bottom: 8px; }
.empty-state a { color: #1a73e8; }

/* ─── Forms ──────────────────────────────── */
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 14px; font-weight: 500; margin-bottom: 4px; color: #444; }

input[type="text"], textarea {
  width: 100%; padding: 10px 12px; font-size: 15px;
  border: 1px solid #d0d0d0; border-radius: 6px;
  outline: none; transition: border-color 0.15s;
  font-family: inherit;
}
input[type="text"]:focus, textarea:focus { border-color: #1a73e8; }

/* ─── Buttons ───────────────────────────── */
.btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 10px 20px; font-size: 15px; font-weight: 500;
  border: none; border-radius: 6px; cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: #1a73e8; color: #fff; }
.btn-primary:hover:not(:disabled) { background: #1557b0; }
.btn-danger { background: #e53e3e; color: #fff; }
.btn-danger:hover:not(:disabled) { background: #c53030; }
.btn-secondary { background: #e8e8e8; color: #333; }
.btn-secondary:hover:not(:disabled) { background: #d5d5d5; }
.btn-ghost { background: transparent; color: #666; padding: 8px 12px; }
.btn-ghost:hover { background: #eee; }

.btn-group { display: flex; gap: 10px; margin-top: 20px; }

/* ─── Toolbar ───────────────────────────── */
.toolbar {
  display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; align-items: center;
}
.toolbar input[type="text"] { flex: 1; min-width: 180px; }
.toolbar select {
  padding: 10px 12px; font-size: 14px; border: 1px solid #d0d0d0; border-radius: 6px;
  background: #fff; outline: none; cursor: pointer;
}

/* ─── Pagination ────────────────────────── */
.pagination {
  display: flex; justify-content: center; align-items: center;
  gap: 12px; margin-top: 20px; font-size: 14px; color: #666;
}
.pagination button { min-width: 36px; }

/* ─── Tabs ──────────────────────────────── */
.tabs { display: flex; gap: 0; margin-bottom: 24px; border-bottom: 2px solid #e0e0e0; }
.tab {
  padding: 10px 24px; font-size: 15px; cursor: pointer; color: #666;
  border-bottom: 2px solid transparent; margin-bottom: -2px;
  background: none; border-top: none; border-left: none; border-right: none;
  transition: color 0.15s, border-color 0.15s;
}
.tab:hover { color: #222; }
.tab.active { color: #1a73e8; border-bottom-color: #1a73e8; font-weight: 500; }

/* ─── Toast ─────────────────────────────── */
.toast {
  position: fixed; top: 20px; right: 20px; z-index: 999;
  padding: 12px 24px; border-radius: 8px; font-size: 14px;
  color: #fff; animation: toastIn 0.3s ease;
}
.toast-info { background: #1a73e8; }
.toast-warn { background: #e67e22; }
.toast-error { background: #e53e3e; }

@keyframes toastIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }

/* ─── Flashcard ─────────────────────────── */
.flashcard-container {
  display: flex; flex-direction: column; align-items: center; gap: 24px;
}
.flashcard {
  width: 100%; max-width: 420px; min-height: 240px;
  perspective: 800px; cursor: pointer;
}
.flashcard-inner {
  position: relative; width: 100%; height: 100%; min-height: 240px;
  transition: transform 0.5s; transform-style: preserve-3d;
}
.flashcard-inner.flipped { transform: rotateY(180deg); }

.flashcard-front, .flashcard-back {
  position: absolute; inset: 0; backface-visibility: hidden;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: #fff; border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.08);
  padding: 32px; text-align: center;
}
.flashcard-front .word-display {
  font-size: 32px; font-weight: 700; color: #1a1a1a;
}
.flashcard-back { transform: rotateY(180deg); }
.flashcard-back .word-display { font-size: 28px; font-weight: 700; }
.flashcard-back .phonetic-display { font-size: 15px; color: #888; margin: 6px 0 12px; }
.flashcard-back .definition-display { font-size: 16px; color: #333; margin-bottom: 12px; }
.flashcard-back .example-display { font-size: 14px; color: #666; font-style: italic; }

.flashcard-actions { display: flex; gap: 16px; }
.flashcard-progress { font-size: 14px; color: #999; }

.flashcard-done { text-align: center; padding: 40px; }
.flashcard-done h2 { font-size: 22px; margin-bottom: 8px; }
.flashcard-done p { color: #888; }

/* ─── Spelling Test ─────────────────────── */
.spelling-container {
  display: flex; flex-direction: column; align-items: center; gap: 20px;
}
.spelling-card {
  background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08);
  padding: 40px; text-align: center; width: 100%; max-width: 480px;
}
.spelling-definition { font-size: 20px; font-weight: 500; color: #333; margin-bottom: 20px; }
.spelling-input { max-width: 320px; text-align: center; font-size: 20px; }
.spelling-feedback { margin-top: 12px; font-size: 15px; }
.spelling-feedback.correct { color: #38a169; }
.spelling-feedback.wrong { color: #e53e3e; }

.spelling-results { text-align: center; }
.spelling-results h2 { font-size: 22px; margin-bottom: 12px; }
.spelling-results .stats { font-size: 18px; margin-bottom: 20px; }
.spelling-results .stats span { font-weight: 700; color: #38a169; }
.spelling-results .stats span.wrong-count { color: #e53e3e; }
.wrong-list {
  text-align: left; background: #fff; border-radius: 8px;
  padding: 16px 20px; margin-bottom: 20px; max-width: 400px;
}
.wrong-list h3 { font-size: 16px; margin-bottom: 8px; color: #e53e3e; }
.wrong-list li { font-size: 14px; padding: 4px 0; list-style: inside; }

/* ─── Export Dropdown ──────────────────── */
.export-wrapper { position: relative; display: inline-block; }
.export-menu {
  position: absolute; top: 100%; right: 0; margin-top: 4px;
  background: #fff; border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  overflow: hidden; z-index: 100; min-width: 120px;
}
.export-menu button {
  display: block; width: 100%; padding: 10px 16px; text-align: left;
  border: none; background: none; font-size: 14px; cursor: pointer;
}
.export-menu button:hover { background: #f0f0f0; }

/* ─── Detail Page ──────────────────────── */
.detail-card {
  background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08);
  padding: 32px;
}
.detail-word { font-size: 32px; font-weight: 700; }
.detail-phonetic { font-size: 16px; color: #888; margin: 4px 0 16px; }
.detail-definition { font-size: 18px; color: #333; margin-bottom: 12px; }
.detail-example { font-size: 15px; color: #666; font-style: italic; margin-bottom: 4px; }
.detail-date { font-size: 13px; color: #aaa; margin-top: 20px; }

/* ─── Modal ────────────────────────────── */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center; z-index: 200;
}
.modal {
  background: #fff; border-radius: 12px; padding: 28px; width: 90%; max-width: 480px;
}
.modal h2 { font-size: 20px; margin-bottom: 16px; }

/* ─── Loading ──────────────────────────── */
.loading { text-align: center; padding: 40px; color: #999; font-size: 15px; }
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/App.css
git commit -m "feat: global CSS styles"
```

---

### Task 7: WordCard 组件 + ExportMenu 组件

**Files:**
- Create: `frontend/src/components/WordCard.jsx`
- Create: `frontend/src/components/ExportMenu.jsx`

- [ ] **Step 1: 创建 frontend/src/components/WordCard.jsx**

```jsx
import { Link } from 'react-router-dom'

export default function WordCard({ word }) {
  return (
    <Link to={`/word/${word.id}`} className="word-card">
      <div className="head">
        <span className="word">{word.word}</span>
        {word.phonetic && <span className="phonetic">{word.phonetic}</span>}
      </div>
      <div className="definition">{word.definition}</div>
    </Link>
  )
}
```

- [ ] **Step 2: 创建 frontend/src/components/ExportMenu.jsx**

```jsx
import { useState, useRef, useEffect } from 'react'
import { exportUrl } from '../api'

export default function ExportMenu({ q, date }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function doExport(format) {
    window.open(exportUrl(format, { q, date }), '_blank')
    setOpen(false)
  }

  return (
    <div className="export-wrapper" ref={ref}>
      <button className="btn btn-secondary" onClick={() => setOpen(!open)}>
        导出
      </button>
      {open && (
        <div className="export-menu">
          <button onClick={() => doExport('json')}>JSON</button>
          <button onClick={() => doExport('csv')}>CSV</button>
          <button onClick={() => doExport('pdf')}>PDF</button>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/WordCard.jsx frontend/src/components/ExportMenu.jsx
git commit -m "feat: WordCard and ExportMenu components"
```

---

### Task 8: WordList 页面

**Files:**
- Create: `frontend/src/pages/WordList.jsx`

- [ ] **Step 1: 创建 frontend/src/pages/WordList.jsx**

```jsx
import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { fetchWords, fetchDates } from '../api'
import WordCard from '../components/WordCard'
import ExportMenu from '../components/ExportMenu'

export default function WordList() {
  const [words, setWords] = useState([])
  const [dates, setDates] = useState([])
  const [q, setQ] = useState('')
  const [date, setDate] = useState('')
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(true)

  useEffect(() => { fetchDates().then(d => setDates(d.dates)).catch(() => {}) }, [])

  useEffect(() => {
    setLoading(true)
    fetchWords({ q, date, page }).then(data => {
      setWords(data.words)
      setTotalPages(data.pages)
    }).finally(() => setLoading(false))
  }, [q, date, page])

  return (
    <div>
      <div className="toolbar">
        <input
          type="text"
          placeholder="搜索单词或释义…"
          value={q}
          onChange={e => { setQ(e.target.value); setPage(1) }}
        />
        <select value={date} onChange={e => { setDate(e.target.value); setPage(1) }}>
          <option value="">全部日期</option>
          {dates.map(d => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
        <ExportMenu q={q} date={date} />
        <Link to="/word/new" className="btn btn-primary">+ 添加</Link>
      </div>

      {loading ? (
        <div className="loading">加载中…</div>
      ) : words.length === 0 ? (
        <div className="empty-state">
          <p>{q || date ? '无匹配单词' : '还没有单词'}</p>
          {q || date ? (
            <button className="btn btn-ghost" onClick={() => { setQ(''); setDate('') }}>
              清除筛选
            </button>
          ) : (
            <Link to="/word/new">去添加第一个单词</Link>
          )}
        </div>
      ) : (
        <>
          {words.map(w => <WordCard key={w.id} word={w} />)}
          {totalPages > 1 && (
            <div className="pagination">
              <button
                className="btn btn-secondary"
                disabled={page <= 1}
                onClick={() => setPage(p => p - 1)}
              >
                上一页
              </button>
              <span>{page} / {totalPages}</span>
              <button
                className="btn btn-secondary"
                disabled={page >= totalPages}
                onClick={() => setPage(p => p + 1)}
              >
                下一页
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 验证**

确保 `/` 页面显示空状态，添加单词后显示列表。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/WordList.jsx
git commit -m "feat: WordList page with search, date filter, and pagination"
```

---

### Task 9: WordNew 页面

**Files:**
- Create: `frontend/src/pages/WordNew.jsx`

- [ ] **Step 1: 创建 frontend/src/pages/WordNew.jsx**

```jsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createWord } from '../api'

export default function WordNew() {
  const [word, setWord] = useState('')
  const [definition, setDefinition] = useState('')
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState(null)
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    if (!word.trim() || !definition.trim()) return
    setLoading(true)
    try {
      const result = await createWord(word, definition)
      if (!result.enriched && result.word.phonetic === '') {
        setToast({ type: 'warn', msg: '音标例句补充失败，可稍后重试' })
        setTimeout(() => {
          setToast(null)
          navigate('/')
        }, 1500)
      } else {
        navigate('/')
      }
    } catch (err) {
      setToast({ type: 'error', msg: err.message })
      setTimeout(() => setToast(null), 3000)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      {toast && <div className={`toast toast-${toast.type}`}>{toast.msg}</div>}
      <h2 style={{ marginBottom: 20 }}>添加单词</h2>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>单词</label>
          <input
            type="text"
            value={word}
            onChange={e => setWord(e.target.value)}
            placeholder="输入英文单词"
            autoFocus
          />
        </div>
        <div className="form-group">
          <label>释义</label>
          <input
            type="text"
            value={definition}
            onChange={e => setDefinition(e.target.value)}
            placeholder="输入中文释义"
          />
        </div>
        <div className="btn-group">
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? '保存中…' : '保存'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => navigate('/')}>
            取消
          </button>
        </div>
      </form>
    </div>
  )
}
```

- [ ] **Step 2: 验证**

访问 `/word/new`，输入 "test" + "测试"，保存。验证跳转回列表、列表有新数据。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/WordNew.jsx
git commit -m "feat: WordNew page with toast feedback"
```

---

### Task 10: WordDetail 页面

**Files:**
- Create: `frontend/src/pages/WordDetail.jsx`

- [ ] **Step 1: 创建 frontend/src/pages/WordDetail.jsx**

```jsx
import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { fetchWord, updateWord, deleteWord } from '../api'

export default function WordDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [word, setWord] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const [editWord, setEditWord] = useState('')
  const [editDef, setEditDef] = useState('')

  useEffect(() => {
    fetchWord(id)
      .then(data => setWord(data.word))
      .catch(() => setError('单词不存在'))
      .finally(() => setLoading(false))
  }, [id])

  function startEdit() {
    setEditWord(word.word)
    setEditDef(word.definition)
    setEditing(true)
  }

  async function handleEdit(e) {
    e.preventDefault()
    const result = await updateWord(id, { word: editWord, definition: editDef })
    setWord(result.word)
    setEditing(false)
  }

  async function handleDelete() {
    if (!window.confirm('确认删除这个单词？')) return
    await deleteWord(id)
    navigate('/')
  }

  if (loading) return <div className="loading">加载中…</div>
  if (error) return (
    <div className="empty-state">
      <p>{error}</p>
      <Link to="/">返回列表</Link>
    </div>
  )

  return (
    <div>
      <Link to="/" className="btn btn-ghost" style={{ marginBottom: 16 }}>← 返回</Link>

      <div className="detail-card">
        <div className="detail-word">{word.word}</div>
        {word.phonetic && <div className="detail-phonetic">{word.phonetic}</div>}
        <div className="detail-definition">{word.definition}</div>
        {word.example && <div className="detail-example">"{word.example}"</div>}
        <div className="detail-date">添加于 {word.created_at.slice(0, 10)}</div>

        <div className="btn-group">
          <button className="btn btn-primary" onClick={startEdit}>编辑</button>
          <button className="btn btn-danger" onClick={handleDelete}>删除</button>
        </div>
      </div>

      {editing && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setEditing(false) }}>
          <div className="modal">
            <h2>编辑单词</h2>
            <form onSubmit={handleEdit}>
              <div className="form-group">
                <label>单词</label>
                <input type="text" value={editWord} onChange={e => setEditWord(e.target.value)} />
              </div>
              <div className="form-group">
                <label>释义</label>
                <input type="text" value={editDef} onChange={e => setEditDef(e.target.value)} />
              </div>
              <div className="btn-group">
                <button type="submit" className="btn btn-primary">保存</button>
                <button type="button" className="btn btn-secondary" onClick={() => setEditing(false)}>取消</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 验证**

从列表点入一个单词 → 查看详情 → 编辑 → 保存 → 删除 → 确认跳转。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/WordDetail.jsx
git commit -m "feat: WordDetail page with edit modal and delete"
```

---

### Task 11: Review 页面 + Flashcard 组件 + SpellingTest 组件

**Files:**
- Create: `frontend/src/pages/Review.jsx`
- Create: `frontend/src/components/Flashcard.jsx`
- Create: `frontend/src/components/SpellingTest.jsx`

- [ ] **Step 1: 创建 frontend/src/components/Flashcard.jsx**

```jsx
import { useState, useEffect, useCallback } from 'react'

export default function Flashcard({ words }) {
  const [queue, setQueue] = useState([])
  const [index, setIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [done, setDone] = useState(false)

  useEffect(() => {
    // 随机打乱
    const shuffled = [...words].sort(() => Math.random() - 0.5)
    setQueue(shuffled)
    setIndex(0)
    setFlipped(false)
    setDone(false)
  }, [words])

  const current = queue[index]

  const handleKey = useCallback((e) => {
    if (!current) return
    if (e.key === ' ') { e.preventDefault(); setFlipped(f => !f) }
    if (!flipped) return
    if (e.key === 'ArrowLeft') handleForgot()
    if (e.key === 'ArrowRight') handleRemember()
  }, [current, flipped])

  useEffect(() => {
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [handleKey])

  function handleForgot() {
    setQueue(prev => [...prev, prev[index]])
    goNext()
  }

  function handleRemember() {
    goNext()
  }

  function goNext() {
    if (index + 1 >= queue.length) {
      setDone(true)
    } else {
      setIndex(i => i + 1)
      setFlipped(false)
    }
  }

  function restart() {
    const shuffled = [...words].sort(() => Math.random() - 0.5)
    setQueue(shuffled)
    setIndex(0)
    setFlipped(false)
    setDone(false)
  }

  if (done) {
    return (
      <div className="flashcard-done">
        <h2>本轮完成</h2>
        <p>已复习 {queue.length} 个单词</p>
        <button className="btn btn-primary" onClick={restart} style={{ marginTop: 16 }}>
          再来一轮
        </button>
      </div>
    )
  }

  if (!current) return <div className="loading">没有单词可复习</div>

  return (
    <div className="flashcard-container">
      <div className="flashcard-progress">
        第 {index + 1} / {queue.length} 个 · 空格翻转 · ← 忘了 · → 记得
      </div>

      <div className="flashcard" onClick={() => setFlipped(f => !f)}>
        <div className={`flashcard-inner ${flipped ? 'flipped' : ''}`}>
          <div className="flashcard-front">
            <span className="word-display">{current.word}</span>
          </div>
          <div className="flashcard-back">
            <span className="word-display">{current.word}</span>
            {current.phonetic && <span className="phonetic-display">{current.phonetic}</span>}
            <span className="definition-display">{current.definition}</span>
            {current.example && <span className="example-display">"{current.example}"</span>}
          </div>
        </div>
      </div>

      {flipped && (
        <div className="flashcard-actions">
          <button className="btn btn-danger" onClick={handleForgot}>忘了</button>
          <button className="btn btn-primary" onClick={handleRemember}>记得</button>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 创建 frontend/src/components/SpellingTest.jsx**

```jsx
import { useState, useEffect } from 'react'

export default function SpellingTest({ words }) {
  const [questions, setQuestions] = useState([])
  const [index, setIndex] = useState(0)
  const [input, setInput] = useState('')
  const [feedback, setFeedback] = useState(null) // { correct: bool, answer: str }
  const [correct, setCorrect] = useState([])
  const [wrong, setWrong] = useState([])
  const [done, setDone] = useState(false)

  useEffect(() => {
    const shuffled = [...words].sort(() => Math.random() - 0.5)
    setQuestions(shuffled)
    setIndex(0)
    setInput('')
    setFeedback(null)
    setCorrect([])
    setWrong([])
    setDone(false)
  }, [words])

  const current = questions[index]

  function handleSubmit(e) {
    e.preventDefault()
    if (!input.trim() || feedback) return
    const isCorrect = input.trim().toLowerCase() === current.word.toLowerCase()
    if (isCorrect) {
      setCorrect(c => [...c, current])
    } else {
      setWrong(c => [...c, current])
    }
    setFeedback({ correct: isCorrect, answer: current.word })
  }

  function handleNext() {
    if (index + 1 >= questions.length) {
      setDone(true)
    } else {
      setIndex(i => i + 1)
      setInput('')
      setFeedback(null)
    }
  }

  function restart(retryWrong = false) {
    const pool = retryWrong ? wrong : [...words].sort(() => Math.random() - 0.5)
    setQuestions(pool)
    setIndex(0)
    setInput('')
    setFeedback(null)
    setCorrect([])
    setWrong([])
    setDone(false)
  }

  if (done) {
    return (
      <div className="spelling-results">
        <h2>测试完成</h2>
        <p className="stats">
          正确 <span>{correct.length}</span> · 错误 <span className="wrong-count">{wrong.length}</span>
        </p>
        {wrong.length > 0 && (
          <div className="wrong-list">
            <h3>错题列表</h3>
            <ul>
              {wrong.map(w => (
                <li key={w.id}><b>{w.word}</b> — {w.definition}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="btn-group" style={{ justifyContent: 'center' }}>
          <button className="btn btn-primary" onClick={() => restart(false)}>重新测试</button>
          {wrong.length > 0 && (
            <button className="btn btn-secondary" onClick={() => restart(true)}>只测错题</button>
          )}
        </div>
      </div>
    )
  }

  if (questions.length === 0) return <div className="loading">没有单词可测试</div>

  return (
    <div className="spelling-container">
      <div className="flashcard-progress">第 {index + 1} / {questions.length} 个</div>

      <div className="spelling-card">
        <div className="spelling-definition">{current.definition}</div>
        <form onSubmit={handleSubmit}>
          <input
            type="text"
            className="spelling-input"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="输入英文拼写"
            autoFocus
            disabled={!!feedback}
          />
          {!feedback && (
            <button type="submit" className="btn btn-primary" style={{ marginTop: 16 }}>
              提交
            </button>
          )}
        </form>
        {feedback && (
          <div className={`spelling-feedback ${feedback.correct ? 'correct' : 'wrong'}`}>
            {feedback.correct ? '✅ 正确！' : `❌ 正确拼写：${feedback.answer}`}
          </div>
        )}
        {feedback && (
          <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={handleNext}>
            {index + 1 >= questions.length ? '查看结果' : '下一题'}
          </button>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 创建 frontend/src/pages/Review.jsx**

```jsx
import { useState, useEffect } from 'react'
import { fetchWords, fetchDates } from '../api'
import Flashcard from '../components/Flashcard'
import SpellingTest from '../components/SpellingTest'

const TABS = [
  { key: 'browse', label: '浏览' },
  { key: 'flashcard', label: '闪卡' },
  { key: 'spelling', label: '拼写测试' },
]

export default function Review() {
  const [tab, setTab] = useState('browse')
  const [words, setWords] = useState([])
  const [dates, setDates] = useState([])
  const [date, setDate] = useState('')
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => { fetchDates().then(d => setDates(d.dates)).catch(() => {}) }, [])

  useEffect(() => {
    setLoading(true)
    fetchWords({ q, date, size: 999 }).then(data => {
      setWords(data.words)
    }).finally(() => setLoading(false))
  }, [q, date])

  return (
    <div>
      <div className="tabs">
        {TABS.map(t => (
          <button
            key={t.key}
            className={`tab ${tab === t.key ? 'active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab !== 'browse' && (
        <div className="toolbar">
          <input
            type="text" placeholder="筛选单词…" value={q}
            onChange={e => setQ(e.target.value)}
          />
          <select value={date} onChange={e => setDate(e.target.value)}>
            <option value="">全部日期</option>
            {dates.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
      )}

      {loading ? (
        <div className="loading">加载中…</div>
      ) : words.length === 0 ? (
        <div className="empty-state"><p>没有单词可供复习</p></div>
      ) : tab === 'browse' ? (
        words.map(w => (
          <div key={w.id} className="word-card">
            <div className="head">
              <span className="word">{w.word}</span>
              {w.phonetic && <span className="phonetic">{w.phonetic}</span>}
            </div>
            <div className="definition">{w.definition}</div>
            {w.example && <div className="example-display" style={{ marginTop: 8, color: '#888' }}>"{w.example}"</div>}
          </div>
        ))
      ) : tab === 'flashcard' ? (
        <Flashcard words={words} />
      ) : (
        <SpellingTest words={words} />
      )}
    </div>
  )
}
```

- [ ] **Step 4: 验证**

访问 `/review` → 切换三个 Tab。闪卡：点击翻转、快捷键、队列循环。拼写：输入 → 提交 → 结果页 → 重测错题。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Review.jsx frontend/src/components/Flashcard.jsx frontend/src/components/SpellingTest.jsx
git commit -m "feat: Review page with browse, flashcard, and spelling test modes"
```

---

### Task 12: 生产构建 & 端到端验证

- [ ] **Step 1: 构建前端**

```bash
cd "/Users/eric_zhou/Projects/Vocabulary_ notebook/frontend"
npm run build
```

确认 `frontend/dist/` 生成，包含 `index.html` 和 `assets/`。

- [ ] **Step 2: 单进程运行验证**

```bash
cd "/Users/eric_zhou/Projects/Vocabulary_ notebook"
source .venv/bin/activate
python app.py
```

打开 `http://localhost:8000`：
- 应显示 React 前端
- 列表页 → 添加单词 → 跳转列表
- 详情页 → 编辑 / 删除
- 复习页 → 三模式切换
- 导出 → 三种格式下载

- [ ] **Step 3: CSV/JSON 导出验证**

```bash
curl -s "http://localhost:8000/api/words/export?format=csv" | head -5
curl -s "http://localhost:8000/api/words/export?format=json" | python3 -m json.tool | head -10
```

- [ ] **Step 4: Commit**

```bash
git add frontend/dist/
git commit -m "feat: production frontend build"
```
