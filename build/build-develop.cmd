chcp 65001
:: ============================================================
::  RemoteConnecter 开发构建脚本
::  PyInstaller -F 单文件 + UPX 压缩 + 各业务模板/静态/ffmpeg 打包
:: ============================================================
set PYINSTALLER_CONFIG_DIR=%~dp0..\.pyinstaller_cache
echo 构建中...
..\python39\python.exe -m PyInstaller -F --upx-dir "..\upx" --add-data "..\main\templates;main/templates" --add-data "..\main\static;main/static" --add-data "..\screen\templates;screen/templates" --add-data "..\screen\static;screen/static" --add-data "..\term\templates;term/templates" --add-data "..\term\static;term/static" --add-data "..\bilimusic\templates;bilimusic/templates" --add-data "..\bilimusic\static;bilimusic/static" --add-data "..\update\templates;update/templates" --add-data "..\update\static;update/static" --add-data "..\shared\static;shared/static" --add-binary "..\bin\ffmpeg.exe;." --collect-all winpty ..\RemoteConnecter.py