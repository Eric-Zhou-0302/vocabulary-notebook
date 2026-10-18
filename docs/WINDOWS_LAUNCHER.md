# Windows 一键启动

先按 README 安装项目的 .venv、requirements.txt，并配置原有的 Ollama 或 DeepSeek；沿用原词库与配置。然后双击根目录 VocabularyBook.exe，自动启动服务并打开页面，无需 Node.js 或额外桌面框架。

双击 create-desktop-shortcut.bat 创建“词汇笔记本”桌面图标；也可运行 powershell -NoProfile -ExecutionPolicy Bypass -File .\install-desktop-shortcut.ps1。快捷方式指向本机安装目录，不开启开机自启，也不覆盖其他目标的同名快捷方式。

重复启动复用当前服务。右下角托盘可重新打开页面、查看日志或安全停止；关闭浏览器不会停止服务。选择“仅退出启动器”会保留服务，下次启动可继续管理。

启动器只监听 127.0.0.1:1400，核对安装目录身份。端口被其他应用或另一份词库占用时不强行终止它们。若旧服务通过 python app.py 启动，启动器可打开它；退出时仍需关闭原启动窗口，再用新入口启动。

不要把 exe 单独移出项目目录。日志和控制文件位于本机 .runtime，不提交 Git。金色书页、云朵图标含 SVG、PNG 和 16–256px ICO，并用于浏览器标签页。

开发者可运行 tools/windows/build-launcher.ps1，使用 Windows 自带 .NET Framework 编译器重建二进制和图标。发行包保留源码，不需要额外下载运行时。

更新时用 Start-Process .\VocabularyBook.exe -ArgumentList '--stop' -Wait -PassThru -WindowStyle Hidden，确认退出码为 0，再备份与更新；--check 可只检查是否已就绪。停止会等待后台写入结束，不强行杀进程。
