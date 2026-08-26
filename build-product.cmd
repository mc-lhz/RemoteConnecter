chcp 65001
:: ============================================================
::  RemoteConnecter 生产构建脚本
::  PyInstaller -F 单文件 + UPX 压缩 + 各业务模板/静态/ffmpeg 打包
::  注意: 不得加 -w(会变为 GUI 子系统, ConPTY 初始化失败 -> 0xc0000142)。
::  改用 --hide-console hide-early: 保持 console 子系统使终端可用, 启动时隐藏黑窗口。
:: ============================================================
set PYINSTALLER_CONFIG_DIR=%~dp0.pyinstaller_cache
echo 构建中...
.\python39\python.exe -m PyInstaller -F --hide-console hide-early --upx-dir "upx" --add-data "main\templates;main/templates" --add-data "main\static;main/static" --add-data "screen\templates;screen/templates" --add-data "screen\static;screen/static" --add-data "term\templates;term/templates" --add-data "term\static;term/static" --add-data "bilimusic\templates;bilimusic/templates" --add-data "bilimusic\static;bilimusic/static" --add-data "update\templates;update/templates" --add-data "update\static;update/static" --add-data "shared\static;shared/static" --add-binary "bin\ffmpeg.exe;." --collect-all winpty RemoteConnecter.py
