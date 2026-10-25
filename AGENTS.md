# 项目说明

## 技术栈
- 后端：Python FastAPI + uvicorn（端口 1400）
- 前端：React + Vite（端口 5173），静态文件构建到 `frontend/dist`
- 部署模式：后端 `python app.py` 直接托管 `frontend/dist`

## 重要规则

**前端代码改动后，必须执行 `cd frontend && npm run build`**

原因：`python app.py` 模式下，后端只读取 `frontend/dist` 的预编译文件，改源码不会自动同步，必须手动 build 才能让改动生效。

## 开发模式

需要热更新时，从项目根目录分别在两个终端启动服务：

```bash
# 后端
./.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 1400 --no-proxy-headers --reload
```

```bash
# 前端
cd frontend && npm run dev -- --host 127.0.0.1
```

前端开发页面为 http://localhost:5173，源码修改会自动更新。日常使用可直接运行 `python app.py`，由后端托管已构建的前端。
