# 安装、更新与本地备份

## 新电脑安装提示词

```text
请在这台电脑安装词汇笔记本：https://github.com/Eric-Zhou-0302/vocabulary-notebook 。先读最新 README 和适用的 AGENTS.md，实际安装项目独立虚拟环境与 requirements.txt，使用随仓库提供的 frontend/dist。按我的选择配置 Ollama 或 DeepSeek；Key 只在本机输入，不贴到聊天或提交 Git。已有安装时保留原词库、复习状态和配置，不克隆覆盖。检查页面、模型状态和原数据；未经要求不发送收费生成，不设置开机自启，不清空数据。最后说明安装目录和启动方式。
```

## 已安装用户的简短更新提示词

```text
请更新本机已安装的词汇笔记本。先读该安装来源的最新 README：停止当前安装的服务 → maintenance.py backup → 检查 Git 状态并快进更新原 origin 的主分支 → 按需更新原虚拟环境依赖、使用附带前端 → maintenance.py verify --backup <实际路径> → 重启并检查原词库、复习进度和配置。保留配置、Key、缓存、备份及未提交修改，不强制重置、不另建空词库、不擅自切换 fork、不发送收费生成。遇到分叉或校验失败保留现场，汇报版本、备份路径和失败环节。
```

首次安装尚无 maintenance.py 的旧版，应先手动在本机另存 words.json 及备份、config.json 和凭据目录，记录 SHA-256 与旧提交，再更新；不能把升级后的状态当作升级前快照。

## 备份工具

先停止本项目服务和托盘启动器（如已安装），用原 .venv 中的 Python 执行：

```bash
python maintenance.py backup
git pull --ff-only origin main
python maintenance.py verify --backup .backups/update-使用上一步实际返回的目录
```

Windows 使用 .venv\Scripts\python.exe，macOS/Linux 使用 .venv/bin/python。若 origin 的默认分支不是 main，应使用实际主分支。

工具保存在本机 .backups：词库、已有缓存备份、真实配置和 .secrets（或 sync.credentials_dir 指定的位置）。包含密钥，不能上传 Git、Drive 或聊天。它检查副本和原件 SHA-256、词数与 FSRS 统计，拒绝对正在运行的缓存操作；不会访问 AI、云端或自动恢复覆盖数据。应用与工具共用缓存锁，启动失败或正常退出均释放锁。

保留旧副本直至验收结束。发现损坏、丢失、分叉或不一致时停止启动，不清理现场、不用旧快照覆盖新记录。
