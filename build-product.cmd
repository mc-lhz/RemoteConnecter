chcp 65001
:: ============================================================
::  RemoteConnecter 生产构建脚本
::  PyInstaller -F -w 单文件 + UPX 压缩 + templates/static/ffmpeg/ffprobe 打包
:: ============================================================
echo 构建中...
pyinstaller -F -w --upx-dir "upx" --add-data "templates;templates" --add-data "static;static" --add-binary "ffmpeg.exe;." --add-binary "ffprobe.exe;." RemoteConnecter.py
