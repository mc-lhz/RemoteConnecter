chcp 65001
:: ============================================================
::  RemoteConnecter 生产构建脚本 (Win7 分支: 已移除终端功能)
::  PyInstaller -F 单文件 + UPX 压缩 + templates/static/ffmpeg/ffprobe 打包
::  使用 Python 3.7 (venv37) + PyInstaller 5.13.2 (不支持 --hide-console)。
::  Win7 无 ConPTY/终端, 可直接用 -w(窗口子系统, 无黑窗口); 输出至 .dist37/.build37。
:: ============================================================
echo 构建中...
pyinstaller -F -w --upx-dir "upx" --add-data "templates;templates" --add-data "static;static" --add-binary "ffmpeg.exe;." --add-binary "ffprobe.exe;." --distpath .dist37 --workpath .build37 --noconfirm RemoteConnecter.py
