chcp 65001
:: ============================================================
::  RemoteConnecter 生产构建脚本
::  PyInstaller -F 单文件 + UPX 压缩 + 各业务模板/静态/ffmpeg 打包
::  注意: 不得加 -w(会变为 GUI 子系统, ConPTY 初始化失败 -> 0xc0000142)。
::  改用 --hide-console hide-early: 保持 console 子系统使终端可用, 启动时隐藏黑窗口。
:: ============================================================
set PYINSTALLER_CONFIG_DIR=%~dp0.pyinstaller_cache
echo 构建中...
.\python39\python.exe -m PyInstaller -F --hide-console hide-early --upx-dir "upx" --add-data "functions\main\templates;functions/main/templates" --add-data "functions\main\static;functions/main/static" --add-data "functions\screen\templates;functions/screen/templates" --add-data "functions\screen\static;functions/screen/static" --add-data "functions\term\templates;functions/term/templates" --add-data "functions\term\static;functions/term/static" --add-data "functions\bilimusic\templates;functions/bilimusic/templates" --add-data "functions\bilimusic\static;functions/bilimusic/static" --add-data "functions\update\templates;functions/update/templates" --add-data "functions\update\static;functions/update/static" --add-data "functions\shared\static;functions/shared/static" --add-binary "bin\ffmpeg.exe;." --collect-all winpty RemoteConnecter.py
