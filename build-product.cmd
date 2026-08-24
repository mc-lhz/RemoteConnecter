chcp 65001
:: ============================================================
::  RemoteConnecter 生产构建脚本
::  PyInstaller -F 单文件 + UPX 压缩 + templates/static/ffmpeg/ffprobe 打包
::  注意: 不得加 -w(会变为 GUI 子系统, ConPTY 初始化失败 -> 0xc0000142)。
::  改用 --hide-console hide-early: 保持 console 子系统使终端可用, 启动时隐藏黑窗口。
:: ============================================================
set PYINSTALLER_CONFIG_DIR=%~dp0.pyinstaller_cache
echo 构建中...
.\python39\python.exe -m PyInstaller -F --hide-console hide-early --upx-dir "upx" --add-data "templates;templates" --add-data "static;static" --add-binary "ffmpeg.exe;." --collect-all winpty RemoteConnecter.py
