# 桌面版开发与打包

macOS 和 Windows 使用 Electron 加载现有 React 界面，后台运行本机 FastAPI 服务。PyInstaller 将 Python 后端打包为独立目录，Electron 安装包携带该目录及 `frontend/dist`。安装后不需要另装 Python 或 Node.js。

源码版 `python app.py` 继续按原方式运行。桌面版仅监听 `127.0.0.1` 的自动分配端口，每次启动使用独立访问令牌；窗口启用沙箱和上下文隔离，不开放 Node.js 权限。应用退出时一并关闭其后端进程。

## 开发启动

从项目根目录运行。需要 Python 3.11+、Node.js 22.13+（22.x）或 24+，依赖安装在项目目录内。

已有网页开发环境时，可复用其 `.venv` 解释器：

```bash
npm --prefix desktop ci
VOCOVE_DESKTOP_PYTHON="$PWD/.venv/bin/python" npm --prefix desktop start
```

桌面开发入口使用已构建的 `frontend/dist`。修改前端后必须执行：

```bash
npm --prefix frontend ci
npm --prefix frontend run build
```

独立 worktree 可以通过 `VOCOVE_DESKTOP_PYTHON` 指向原项目的解释器，不需要复制或读取原项目词库。该变量必须使用解释器的绝对路径；它只选择 Python，不选择数据目录。

首次启动会创建空词库使用的配置，默认选择 Ollama 且不含 API Key。到「设置与工具 → 模型设置」填写实际模型。桌面包不包含 Ollama 服务或模型权重，也不替用户创建 DeepSeek 账号。

## 数据目录与迁移

正式应用默认保存数据的位置：

| 系统 | 数据目录 |
| --- | --- |
| macOS | `~/Library/Application Support/Vocove/data` |
| Windows | `%APPDATA%\Vocove\data` |

源码开发默认使用 `Vocove Dev` 目录，避免与安装版混用。应用菜单可打开数据目录。自动验证可将 `VOCOVE_DESKTOP_USER_DATA_DIR` 指向专用临时目录；后端数据会放在该目录的 `data` 子目录。

首次升级会将原桌面数据完整复制到新的默认目录，并保留原副本；已有 Vocove 数据不会被覆盖。升级前应退出原应用，数据仍被占用时启动会停止并提示。显式指定用户数据目录或运行冒烟检查时，不执行自动迁移。

词库与备份、`config.json`、`.secrets` 均保存在数据目录内，不写入 `.app`、安装目录或源码仓库。更换程序文件不会替换这些数据；卸载 Windows 程序默认保留应用数据。卸载或删除应用本身不能代替完整备份。

从网页模式迁移：

1. 在原应用「同步与备份」下载完整备份，并保留原词库和配置。
2. 在桌面应用的同一页面导入该备份。普通列表 PDF / CSV / JSON 导出不能代替完整学习历史备份。
3. 在桌面应用重新配置模型和 Google Drive 授权。API Key 与 OAuth 凭据不会随完整词库备份自动迁移。
4. 核对单词本、复习进度和导出功能后，再决定日常使用哪个入口。网页和桌面各自保存独立数据；只有主动配置同步后才交换词库变更。

桌面版保留现有 PDF 字体规则：macOS 尝试系统 Arial Unicode；Windows 如需导出中文和音标，应将 `VOCOVE_CJK_FONT` 设置为覆盖所需字形的静态 `.ttf` / `.otf` 字体绝对路径。该环境变量需在启动应用前设置；不支持 TTC 或可变字体。安装包不附带第三方字体，缺少字体时可先导出 CSV / JSON。

## 构建安装包

必须在目标操作系统及架构上构建后端与 Electron 应用。Windows 包需要 Windows 构建环境，macOS Intel 和 Apple Silicon 也分别构建；不能把本机生成的后端拷到另一平台打包。

### macOS

在项目根目录创建专用打包环境：

```bash
python3.11 -m venv .venv-desktop
./.venv-desktop/bin/python -m pip install -r requirements-desktop.txt
npm --prefix frontend ci
npm --prefix desktop ci
VOCOVE_DESKTOP_PYTHON="$PWD/.venv-desktop/bin/python" npm --prefix desktop run dist
```

### Windows PowerShell

```powershell
py -3.11 -m venv .venv-desktop
.\.venv-desktop\Scripts\python.exe -m pip install -r requirements-desktop.txt
npm --prefix frontend ci
npm --prefix desktop ci
$env:VOCOVE_DESKTOP_PYTHON = (Resolve-Path .\.venv-desktop\Scripts\python.exe).Path
npm --prefix desktop run dist
```

`dist` 先构建前端，再用 PyInstaller 打包后端，最后生成当前平台的安装包。`npm --prefix desktop run pack` 执行相同准备步骤，但只生成可运行的应用目录，适合本地验收。

| 路径 | 内容 |
| --- | --- |
| `desktop/build/backend/vocove-backend/` | 当前平台的 Python 后端及运行依赖 |
| `desktop/release/` | Electron 应用目录与安装包 |
| `desktop/package-lock.json` | Electron 与打包工具依赖锁 |
| `requirements-desktop.txt` | 后端运行依赖及 PyInstaller 打包依赖 |
| `desktop/resources/` | 打包使用的应用图标、DMG 背景及 NSIS 位图 |
| `desktop/artwork/` | 图标母版、生成提示词、安装图 SVG 母版与资源清单 |

打包输入仅包含程序代码、前端构建和所需依赖，不包含真实词库、配置或凭据。输出目录、虚拟环境和 `node_modules` 不提交 Git。

在 macOS 上，可在仓库根目录运行 `desktop/node_modules/.bin/electron desktop/artwork/installers/render.cjs` 重新导出安装图，结果位于 `desktop/build/installer-artwork/`。DMG 的 1× / 2× PNG 需同时保留；Windows 页眉和侧栏需转换为 24 位 RGB BMP，再更新 `desktop/resources/` 中的文件。图标与安装图的尺寸、用途见 `desktop/artwork/assets.json`。

## 检查与平台验收

在已有开发测试环境中运行：

```bash
make check
npm --prefix desktop test
```

源码模式可运行桌面冒烟检查：

```bash
VOCOVE_DESKTOP_PYTHON="$PWD/.venv/bin/python" npm --prefix desktop run smoke
```

`--smoke-test` 自动创建系统临时目录 `vocove-desktop-smoke-*`，使用无密钥测试配置并阻止页面访问外网；验证页面、访问隔离、SSE、词汇编辑、复习、备份导入及文件导出后自动退出。成功输出 `DESKTOP_SMOKE_OK` 并返回 0，失败输出 `DESKTOP_SMOKE_FAILED` 并返回 1。临时目录保留用于排查，不会自动删除；如通过 `VOCOVE_DESKTOP_USER_DATA_DIR` 指定目录，模式会拒绝已有数据，避免读入日常词库。打包后的应用可直接附加 `--smoke-test` 参数进行同样检查。

桌面验收应使用专用临时数据目录，至少检查首次启动、页面和静态资源加载、增删改查、复习、文件导入导出、退出后后端清理，以及再次启动后数据保留。涉及模型和 Google OAuth 的真实验证需单独授权、配置，不属于离线自动测试。

macOS 上通过检查，只说明该架构的应用可运行；Windows 安装、卸载和应用运行需要在 Windows 上分别验证。未完成的项目应记录为未验收，不能以生成安装包代替功能验证。

`.github/workflows/desktop-build.yml` 在推送到 `codex/desktop-packaging` 时自动运行，也保留 `workflow_dispatch` 手动入口；在 macOS Apple Silicon、macOS Intel 和 Windows x64 上分别检查、打包和运行桌面冒烟验收。Windows 还会在 GitHub 托管 runner 的独立临时目录中静默运行 NSIS 安装包，确认安装后的应用通过冒烟检查，再等待静默卸载完成，检查安装文件及注册表项已移除；成功或失败后都会清理本次临时目录。安装验收脚本拒绝在本机运行。同一分支的新运行会取消尚未完成的旧运行。工作流仅上传构建文件供下载，不自动发布 GitHub Release；提交、推送或运行远程工作流需按项目权限约定处理。

分支的 `push` 触发不要求将桌面工作流合入默认分支，因此桌面分支可以独立验收。手动入口要求默认分支包含该工作流。见 [GitHub 工作流触发规则](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#push)。也可按上面的命令在 Windows 或另一台 Mac 上本地构建。

## 签名与分发

当前流程用于开发测试，没有配置 Apple Developer ID 公证或 Windows 发布证书。macOS 本地构建可能采用临时签名；这不等同于可公开分发的 Developer ID 签名与公证。系统可能阻止或提示未知来源程序，不应为验证应用关闭系统安全功能。

公开分发前，需要配置相应证书和签名、公证流程，并在干净机器上验证安装、启动、升级和卸载。此版本不包含自动更新服务。
