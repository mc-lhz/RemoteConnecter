chcp 65001
:: ============================================================
::  RemoteConnecter 生产构建脚本
::  PyInstaller -F 单文件 + UPX 压缩 + 各业务模板/静态/ffmpeg 打包
::  注意: 不得加 -w(会变为 GUI 子系统, ConPTY 初始化失败 -> 0xc0000142)。
::  改用 --hide-console hide-early: 保持 console 子系统使终端可用, 启动时隐藏黑窗口。
::  注意: 不用 --collect-submodules functions 收集业务模块。
::  嵌入版 Python 的 python39._pth 限制了 sys.path 且忽略 PYTHONPATH,
::  导致 spec 顶层 collect_submodules('functions') 返回空列表, functions.*
::  子模块全部漏进 PYZ。故此处改为显式 --hidden-import 逐个罗列(与下方
::  --add-data 逐业务罗列风格一致), 保证每个业务 _bp 模块被打进 PYZ。
::  运行时 pkgutil 蓝图自动扫描依赖 pyi_rth_pkgutil 钩子, 不受影响。
::  新增业务时: 在 functions/xxx/ 下新建 xxx_bp.py, 并在此处加一行 --hidden-import。
:: ============================================================
set PYINSTALLER_CONFIG_DIR=%~dp0.pyinstaller_cache
echo 构建中...
.\python39\python.exe -m PyInstaller -F --noconfirm --hide-console hide-early --upx-dir "upx" --hidden-import functions.bilimusic.bilimusic_bp --hidden-import functions.main.main_bp --hidden-import functions.main.file_bp --hidden-import functions.screen.screen_bp --hidden-import functions.term.term_bp --hidden-import functions.update.update_bp --hidden-import functions.shared --add-data "functions\main\templates;functions/main/templates" --add-data "functions\main\static;functions/main/static" --add-data "functions\screen\templates;functions/screen/templates" --add-data "functions\screen\static;functions/screen/static" --add-data "functions\term\templates;functions/term/templates" --add-data "functions\term\static;functions/term/static" --add-data "functions\bilimusic\templates;functions/bilimusic/templates" --add-data "functions\bilimusic\static;functions/bilimusic/static" --add-data "functions\update\templates;functions/update/templates" --add-data "functions\update\static;functions/update/static" --add-data "functions\shared\static;functions/shared/static" --add-binary "bin\ffmpeg.exe;bin" --collect-all winpty RemoteConnecter.py
