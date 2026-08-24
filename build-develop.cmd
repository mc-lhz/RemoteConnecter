chcp 65001
:: ============================================================
::  RemoteConnecter 开发构建脚本
::  PyInstaller -F 单文件 + UPX 压缩 + templates/static/ffmpeg/ffprobe 打包
:: ============================================================
set PYINSTALLER_CONFIG_DIR=%~dp0.pyinstaller_cache
echo 构建中...
.\python39\python.exe -m PyInstaller -F --upx-dir "upx" --add-data "templates;templates" --add-data "static;static" --add-binary "ffmpeg.exe;." --collect-all winpty RemoteConnecter.py