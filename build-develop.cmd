chcp 65001
:: ============================================================
::  RemoteConnecter 开发构建脚本
::  PyInstaller -F 单文件 + UPX 压缩 + templates/static/ffmpeg/ffprobe 打包
:: ============================================================
echo 构建中...
pyinstaller -F --upx-dir "upx" --add-data "templates;templates" --add-data "static;static" --add-binary "ffmpeg.exe;." --add-binary "ffprobe.exe;." --distpath .dist37 --workpath .build37 --noconfirm RemoteConnecter.py