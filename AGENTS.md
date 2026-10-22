# 项目说明

## 技术栈
- 后端：Python FastAPI + uvicorn（端口 1400）
- 前端：React + Vite（端口 5173），静态文件构建到 `frontend/dist`
- 部署模式：后端 `python app.py` 直接托管 `frontend/dist`

## 重要规则

**前端代码改动后，必须执行 `cd frontend && npm run build`**

原因：`python app.py` 模式下，后端只读取 `frontend/dist` 的预编译文件，改源码不会自动同步，必须手动 build 才能让改动生效。

## 开发模式（推荐）

```bash
./start.sh
```

同时启动后端（uvicorn with --reload）和前端（Vite 热更新），前端改代码秒级生效。
