# 词汇笔记本 — 设计文档

## 概述

一个 Web 词汇管理应用。用户在"不背单词"App 中背单词时，将重点/易忘单词手动录入本系统，通过浏览、闪卡、拼写测试三种模式加强记忆。支持搜索和导出（JSON/CSV/PDF）。

## 技术栈

| 层 | 选型 |
|---|------|
| 前端 | React SPA + Vite |
| 后端 | Python FastAPI |
| 存储 | 本地 JSON 文件 |
| LLM | 本地 Ollama (gemma4:26b)，保存时自动补充音标+例句 |
| PDF 生成 | WeasyPrint (HTML + CSS → PDF) |
| Python 环境 | `.venv` 虚拟环境 |

## 架构

```
┌──────────────────┐     REST API      ┌──────────────────┐
│  React SPA       │ ◄───────────────► │  FastAPI (:8000) │
│  (dev: :5173)    │                   │                  │
└──────────────────┘                   │  ┌────────────┐  │
                                       │  │ words.json │  │
                                       │  └────────────┘  │
                                       │  ┌────────────┐  │
                                       │  │ Ollama API │  │
                                       │  └────────────┘  │
                                       └──────────────────┘
```

- **日常使用**：`python app.py` 单进程，FastAPI 同时提供 API 和打包后的 React 静态文件，访问 `localhost:8000`
- **开发时**：前端 `npm run dev` 独立开 Vite HMR 服务器，Vite 代理 API 请求到 FastAPI

## 数据模型

```json
// words.json
{
  "words": [
    {
      "id": "uuid-v4",
      "word": "ephemeral",
      "definition": "短暂的，转瞬即逝的",
      "phonetic": "/ɪˈfemərəl/",
      "example": "The beauty of cherry blossoms is ephemeral.",
      "created_at": "2026-06-02T10:30:00+08:00"
    }
  ]
}
```

字段说明：
- `id`：UUID v4，后端生成
- `word`：单词原文
- `definition`：用户输入的中文释义
- `phonetic`：音标，保存时由 Ollama 自动补充，失败则留空
- `example`：例句，保存时由 Ollama 自动补充，失败则留空
- `created_at`：ISO 8601 带时区

## API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/words` | 单词列表，支持 `?q=` 搜索、`?date=` 按日期筛选、`?page=&size=` 分页 |
| GET | `/api/words/{id}` | 单词详情 |
| POST | `/api/words` | 新增单词，保存后异步调用 Ollama 补充音标+例句，完整记录返回前端 |
| PUT | `/api/words/{id}` | 编辑单词（仅可编辑 word/definition） |
| DELETE | `/api/words/{id}` | 删除单词 |
| GET | `/api/words/export?format=json\|csv\|pdf` | 导出全部或筛选后的单词 |
| GET | `/api/dates` | 获取有记录的日期列表，按日期降序 |

### POST /api/words 流程

1. 前端 POST `{ "word": "...", "definition": "..." }`
2. 后端生成 UUID、写入当前时间戳
3. 后端调用 Ollama API，prompt 要求返回 `{ "phonetic": "...", "example": "..." }`
4. 解析 LLM 返回，填入 `phonetic` 和 `example` 字段
5. 写入 JSON 文件
6. 返回完整 word 对象给前端

### Ollama 调用失败处理

- Ollama 不可用/超时/返回格式不正确 → `phonetic` 和 `example` 留空，前端提示"音标例句补充失败，可稍后重试"
- 单词本身不丢失

## 前端页面结构

```
/                    单词列表页（首页）
/word/new            新增单词页
/word/:id            单词详情页
/review              复习页面（三模式 Tab）
```

### 单词列表页 `/`
- 顶部：搜索框 + 日期筛选下拉 + 导出按钮（下拉选格式）
- 列表区：单词卡片（词/音标/释义缩略），点击进入详情
- 底部：分页
- 空列表：引导文案"还没有单词，去添加第一个吧"

### 新增单词页 `/word/new`
- 单词输入框
- 释义输入框
- 保存按钮 → POST 后跳回列表页
- 保存期间 loading 状态

### 单词详情页 `/word/:id`
- 展示：单词、音标、释义、例句、创建日期
- 编辑按钮 → 弹出编辑框，仅可修改单词/释义
- 删除按钮 → 确认后删除，跳回列表

### 复习页 `/review`
三个 Tab 切换：浏览 | 闪卡 | 拼写测试

#### 浏览模式
- 全列表展示，单词及其释义/音标/例句直接可见
- 支持搜索过滤

#### 闪卡模式
- 正面只显示单词，点击或按空格翻转
- 翻转后显示：单词 + 音标 + 释义 + 例句
- 两个按钮："忘了"（放回队列末尾）、"记得"（本轮移除）
- 键盘快捷键：空格=翻转，←=忘了，→=记得
- 进度指示：第 X / N 个
- 本轮结束提示"本轮完成"

#### 拼写测试
- 显示中文释义，用户输入英文拼写
- 提交后判断：大小写不敏感，忽略首尾空格
- 正确 → 绿色提示，错误 → 显示正确拼写
- 题干顺序随机打乱
- 全部完成后显示成绩：正确/错误数量 + 错题列表
- 可一键"重测错题"

## PDF 导出设计

- 技术：WeasyPrint 渲染 HTML 模板 → PDF
- 排版：每个单词一个独立卡片，分隔线区分，阅读不串行
- 字体：Georgia (serif) 正文 + Helvetica (sans-serif) 词头
- `break-inside: avoid` 保证单词卡片不跨页
- 页眉：标题 + 导出日期，页脚：页码
- A4 尺寸，打印友好

## 错误处理 & 边界情况

| 场景 | 处理 |
|------|------|
| Ollama 不可用 | 单词正常保存，音标/例句留空，前端 toast 提示 |
| JSON 文件不存在/损坏 | 启动时自动创建空 `{ "words": [] }` |
| 空列表 | 空状态引导文案 |
| 搜索无结果 | "无匹配单词" + 清除搜索按钮 |
| 重复单词 | 不去重（同一天可能记录不同释义） |
| 404 单词 | 详情页显示"单词不存在"，提供返回链接 |

## 项目目录结构

```
Vocabulary_ notebook/
├── .venv/                 # Python 虚拟环境
├── CLAUDE.md              # 项目环境说明
├── app.py                 # FastAPI 入口
├── requirements.txt
├── words.json             # 数据存储
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── api.js         # API 请求封装
│       ├── pages/
│       │   ├── WordList.jsx
│       │   ├── WordDetail.jsx
│       │   └── Review.jsx
│       └── components/
│           ├── WordCard.jsx
│           ├── Flashcard.jsx
│           ├── SpellingTest.jsx
│           └── ExportMenu.jsx
├── templates/
│   └── pdf_export.html    # WeasyPrint 模板
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-06-02-vocabulary-notebook-design.md
```

## 不包含

- 用户认证/多用户
- 间隔重复 (SRS / SM-2)
- 自定义标签/分类
- 从不背单词自动导入
- 部署到远程服务器
