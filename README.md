<div align="center">
  <h1>📖 Vocabulary Notebook</h1>
  <p><strong>把单词记下来，也真正记住它。</strong></p>
  <p>
    一个本地优先的 AI 词汇笔记本。写下单词，自动补全音标、释义与例句，
    <br />
    再用 FSRS 间隔复习，把“见过”变成“记得”。
  </p>
  <p>
    <a href="https://github.com/Eric-Zhou-0302/vocabulary-notebook">
      <img alt="Local-first" src="https://img.shields.io/badge/Local--first-Your_Data-9b7137?style=for-the-badge&labelColor=292522" />
    </a>
    <a href="https://fastapi.tiangolo.com/">
      <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&labelColor=292522" />
    </a>
    <a href="https://react.dev/">
      <img alt="React" src="https://img.shields.io/badge/React-Frontend-61dafb?style=for-the-badge&labelColor=292522" />
    </a>
    <a href="https://opensource.org/licenses/MIT">
      <img alt="License" src="https://img.shields.io/badge/License-MIT-8b5cf6?style=for-the-badge&labelColor=292522" />
    </a>
  </p>
</div>

<p align="center">
  <img
    src="assets/vocabulary-notebook-cover.jpg"
    alt="Vocabulary Notebook — 本地优先的 AI 词汇笔记本"
    width="960"
  />
</p>

---

## 它做什么

很多单词软件让你记住一个账号，却不一定让你记住单词。

Vocabulary Notebook 把词库留在本地：添加一个单词后，Ollama 或 DeepSeek 会在后台补全 IPA 音标、中文释义和例句；学完之后，FSRS 根据你的真实记忆状态安排下一次复习。

| 能力 | 体验 |
|---|---|
| **AI 自动补全** | 只输入单词，后台生成音标、中文释义和自然例句 |
| **实时进度** | SSE 推送补全过程，不用轮询，也不用手动刷新 |
| **每日复习** | FSRS-4.5 调度，按“重来 / 困难 / 良好 / 简单”调整间隔 |
| **全部单词** | 按 A–Z 或随机顺序翻卡，不改动复习进度 |
| **主动回忆** | 闪卡和拼写测试并存，不只做选择题式识别 |
| **随时带走** | 一键导出 PDF、CSV 或 JSON，数据不被平台锁住 |
| **舒服耐看** | 深色 / 浅色主题，简体 / 繁体切换，完整键盘操作 |

---

## 快速开始

### 1. 获取项目

```bash
git clone https://github.com/Eric-Zhou-0302/vocabulary-notebook.git
cd vocabulary-notebook
```

### 2. 安装后端依赖

使用项目独立虚拟环境，避免污染系统 Python：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.json.example config.json
```

### 3. 构建前端

```bash
cd frontend
npm install
npm run build
cd ..
```

### 4. 启动

```bash
python app.py
```

打开 [http://localhost:1400](http://localhost:1400)，你的词库就在那里。

> 正在开发？运行 `./start.sh`，它会同时启动 FastAPI 热重载服务和 Vite 开发服务器。前端地址为 [http://localhost:5173](http://localhost:5173)。

---

## 使用

### 写下一个单词

点击“添加单词”，输入拼写即可。应用会立即保存记录，并把 AI 补全任务放到后台；音标、释义和例句生成后会实时出现在页面上。

### 每天复习

进入“复习”页，先回忆，再翻面：

| 按键 | 操作 |
|---|---|
| `Space` / `Enter` | 翻开当前卡片 |
| `1` | 重来 |
| `2` | 困难 |
| `3` | 良好 |
| `4` | 简单 |
| `←` / `→` | 在“全部单词”模式切换卡片 |

每次评分都会更新该词的难度、稳定性和下次复习时间。选择“重来”的卡片会回到本轮队尾，不会偷偷溜走。

### 回看整本词库

切换到“全部单词”，可以按 A–Z 浏览，也可以洗牌随机复习。这个模式只读，不提交评分、不消耗每日新词额度，也不会改变 SRS 状态。

### 导出

当前筛选结果可以导出为：

- **PDF**：适合打印和离线阅读，内置 CJK 字体支持
- **CSV**：适合 Excel、Numbers 或进一步分析
- **JSON**：完整备份，方便迁移与二次开发

---

## 选择你的 AI

编辑根目录下的 `config.json`。词库始终保存在本地；只有选择云端 Provider 时，待补全的单词内容才会发送给对应服务。

### Ollama：本地运行

```json
{
  "provider": "ollama",
  "ollama": {
    "url": "http://localhost:11434/api/generate",
    "model": "gemma4:26b"
  }
}
```

启动模型后即可使用：

```bash
ollama serve
ollama run gemma4:26b
```

模型名称可以替换；修改后同步更新 `config.json` 中的 `model`。

### DeepSeek：云端调用

```json
{
  "provider": "deepseek",
  "deepseek": {
    "api_key": "sk-你的-key",
    "model": "deepseek-chat"
  }
}
```

API Key 可在 [DeepSeek 开放平台](https://platform.deepseek.com/api_keys)创建。不要提交真实的 `config.json`。

---

## 复习机制

每日复习使用 FSRS-4.5，根据每个单词的难度（Difficulty）与记忆稳定性（Stability）估算遗忘概率，并动态安排下一次出现的时间。

```text
添加单词
   │
   ├── AI 补全音标、释义、例句
   │
   ▼
首次复习 ──评分──> 更新记忆状态 ──> 计算下次到期时间
   ▲                                      │
   └──────────────── 到期后重新进入队列 ──┘
```

- 默认每天引入 20 个新词
- 评分按钮会预览预计的下次间隔
- 新词额度由首次复习时间推导，重启服务不会清零
- 旧词无需迁移，第一次评分时才写入 `srs` 字段
- 顶部“复习”角标会显示当前待复习数量

调整每日新词上限：

```json
{
  "srs": {
    "daily_new_limit": 20
  }
}
```

---

## 工作流

```text
┌─────────────────┐       REST + SSE       ┌──────────────────────┐
│ React + Vite UI │ ◄────────────────────► │ FastAPI · port 1400  │
└─────────────────┘                         └──────────┬───────────┘
                                                     │
                              ┌──────────────────────┼──────────────────┐
                              ▼                      ▼                  ▼
                        words.json          Ollama / DeepSeek       FSRS-4.5
                       本地原子写入           AI 内容补全           复习调度
```

后端会用锁保护读写，并通过临时文件原子替换 `words.json`；检测到数据损坏时会保留备份。前端构建产物由 FastAPI 直接托管，因此部署时不需要额外的 Web 服务。

---

## 项目结构

```text
vocabulary-notebook/
├── app.py                 # FastAPI 应用、API、SSE 与静态文件托管
├── config.py              # Provider 与 SRS 配置
├── fsrs.py                # FSRS-4.5 调度算法
├── words.json             # 本地词库，已被 Git 忽略
├── templates/             # PDF 导出模板
├── tests/                 # 后端、提示词与复习测试
└── frontend/
    ├── src/
    │   ├── pages/         # 单词列表、详情、新建、复习
    │   ├── components/    # 闪卡、导出、模型状态等组件
    │   └── api.js         # 前端 API 封装
    └── dist/              # 生产构建产物
```

---

## 开发与验证

启动前后端开发服务：

```bash
./start.sh
```

运行后端测试：

```bash
./.venv/bin/pytest -q
```

前端代码修改后必须重新构建，FastAPI 才能托管最新版本：

```bash
cd frontend && npm run build
```

---

## 数据与隐私

- 单词、复习状态和历史记录只写入本机 `words.json`
- `words.json` 与真实 `config.json` 均不会进入 Git
- Ollama 模式可以完全本地运行
- DeepSeek 模式会把补全请求发送到 DeepSeek API，请按自己的隐私要求选择

你的词库不是平台的人质。它只是一个你随时能打开、备份和带走的 JSON 文件。

---

## License

[MIT](https://opensource.org/licenses/MIT) © 2026 [Eric Zhou](https://ericzhou.net/)
