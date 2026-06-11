# 词汇笔记本

> 你的第二大脑 — 完全本地运行，无云依赖，无隐私泄露

一个本地优先的词汇笔记本，用你自己的 LLM（Ollama 或 DeepSeek）自动补全每个单词的 IPA 音标、中文释义和例句。数据存在你自己的机器上，零云依赖。

## 功能

| 功能 | 说明 |
|---|---|
| **AI 自动补全** | 添加单词 → LLM 后台自动填充音标、释义、例句 |
| **实时 SSE 推送** | 补全进度通过 Server-Sent Events 推送到 UI，无需轮询或刷新 |
| **闪卡模式** | 随机顺序 + 翻转 + 自我评分（← 忘了 / → 记住了），键盘驱动 |
| **拼写测试** | 回忆型练习——输入拼写，而非识别选项 |
| **PDF / CSV / JSON 导出** | 可打印 PDF（含 CJK 字体，零系统依赖）、CSV、JSON 备份 |
| **多 Provider** | 通过 `config.json` 在 Ollama（本地免费）和 DeepSeek（云端）间切换 |
| **深色 / 浅色主题** | 暖色调纸感美学——`#1a1817` 深色、`#f5f0e8` 暖色浅色 |
| **繁体 / 简体** | 界面一键切换繁/简 |

## 快速启动

```bash
# 1. 克隆
git clone https://github.com/YOUR_USERNAME/vocabulary-notebook.git
cd vocabulary-notebook

# 2. 后端
pip install -r requirements.txt
cp config.json.example config.json
# 编辑 config.json → 设置你的 Ollama URL 和模型

# 3. 前端
cd frontend && npm install && npm run build && cd ..

# 4. 启动
python app.py
# → 访问 http://localhost:1400
```

**Ollama 配置**（本地模型）：
```bash
ollama run gemma4:26b
```

**DeepSeek 配置**（云端）：
```json
// config.json
{
  "provider": "deepseek",
  "deepseek": {
    "api_key": "sk-...",
    "model": "deepseek-chat"
  }
}
```

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│  React SPA (frontend/dist)                         │
│  ┌─────────┐  ┌──────────┐  ┌────────────────────┐ │
│  │WordList │  │  Review  │  │  WordDetail        │ │
│  └────┬────┘  └────┬─────┘  └─────────┬──────────┘ │
└───────┼────────────┼───────────────────┼────────────┘
        │            │                    │
        └────────────┴────────┬───────────┘
                             │ REST + SSE
        ┌────────────────────▼───────────┐
        │     FastAPI (app.py :1400)     │
        │  ┌─────────────────────────┐   │
        │  │  SSE Event Bus          │   │
        │  │  (asyncio.Queue + Worker)│  │
        │  └───────────┬─────────────┘   │
        │              │                │
        │  ┌───────────▼──────────┐     │
        │  │  Ollama / DeepSeek    │     │
        │  │  enrich_word()        │     │
        │  └───────────────────────┘     │
        └───────────────────────────────┘
                             │
        ┌────────────────────▼───────────┐
        │        words.json              │
        └───────────────────────────────┘
```

## 技术栈

- **后端**：FastAPI，fpdf2（纯 Python PDF，零系统字体依赖），SSE，threading.RLock 原子写入
- **前端**：React 18，React Router v6，Vite 6，纯 CSS（无 Tailwind，无 UI 库）
- **LLM**：Ollama（本地）或 DeepSeek（云端），通过 `config.json` 配置
- **数据**：单个 JSON 文件，`.tmp` 原子交换写入，损坏时自动备份

## 项目结构

```
vocabulary-notebook/
├── app.py              # FastAPI 后端 + 所有 API 路由
├── config.py           # Provider 配置加载器
├── config.json.example # 配置模板
├── requirements.txt    # Python 依赖
├── words.json          # 数据存储（已被 .gitignore 排除）
├── frontend/
│   ├── src/
│   │   ├── api.js          # Fetch 封装
│   │   ├── App.jsx         # 路由 + 布局
│   │   ├── pages/          # WordList, WordNew, WordDetail, Review
│   │   ├── components/     # Flashcard, SpellingTest, ExportMenu,
│   │   │                   # ModelStatus, EnrichProgress, ThemeToggle...
│   │   ├── useSSE.js       # SSE Hook
│   │   └── useEnrichProgress.js
│   └── dist/           # 构建产物（gitignored）
└── CLAUDE.md           # 项目文档
```

## 为什么做这个？

市面上的背单词工具大多需要联网、数据存在别人服务器上、AI 补全需要付费 API。

这个工具：**数据归你，模型归你，运行也在你本地。**

## License

MIT