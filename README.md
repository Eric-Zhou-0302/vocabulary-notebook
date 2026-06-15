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
| **间隔复习（SRS）** | FSRS-4.5 调度，4 档评分，下次间隔预览，新词每日上限 |

## 快速启动

```bash
# 1. 克隆
git clone https://github.com/Eric-Zhou-0302/vocabulary-notebook.git
cd vocabulary-notebook

# 2. 后端
pip install -r requirements.txt
cp config.json.example config.json

# 3. 前端
cd frontend && npm install && npm run build && cd ..

# 4. 启动
python app.py
# → 访问 http://localhost:1400
```

## 配置 LLM Provider

编辑 `config.json`，支持两种 Provider：

### Ollama（本地，免费）

```json
{
  "provider": "ollama",
  "ollama": {
    "url": "http://localhost:11434/api/generate",
    "model": "gemma4:26b"
  }
}
```

1. 确保 Ollama 运行中：`ollama serve`（或系统已自启动）
2. 下载并运行模型：`ollama run gemma4:26b`（支持任意模型，换模型后同步修改 `config.json` 中的 `model` 字段）
3. 验证连接：`curl http://localhost:11434/api/tags`（返回模型列表即正常）

### DeepSeek（云端，按量付费）

```json
{
  "provider": "deepseek",
  "deepseek": {
    "api_key": "sk-你的key",
    "model": "deepseek-chat"
  }
}
```

从 [DeepSeek API Keys](https://platform.deepseek.com/api_keys) 获取 key。

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

## 间隔复习（SRS）

复习 tab 用 FSRS-4.5 算法做间隔重复调度：
- **4 档评分**：重来 (1) / 困难 (2) / 良好 (3) / 简单 (4)
- **键盘**：空格翻面，1-4 评分
- **下次间隔预览**：每个按钮显示 FSRS 算出的预测间隔（如 "5d" / "2mo"）
- **新词每日上限**：默认 20/天（可在 `app.py` 顶部 `DAILY_NEW_LIMIT` 调整）
- **Again 重学**：本 session 内重学一次，同时 `lapses++`
- 顶部 nav 的 "复习" 链接会显示金色角标 `· N` 提示待复习数（60s 轮询）

## License

MIT