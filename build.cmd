@echo off
chcp 65001 >nul
cd /d %~dp0
setlocal enabledelayedexpansion
set "PYINSTALLER_CONFIG_DIR=%~dp0.pyinstaller_cache"
REM ============================================================
REM  RemoteConnecter build script (single entry, pure cmd)
REM  PyInstaller -F onefile + UPX, auto scan functions/ packages.
REM  No -w: GUI subsystem breaks ConPTY init (0xc0000142).
REM  Default: production build, console hidden (hide-console hide-early).
REM  Debug: run build.cmd --show-console to keep the console window.
REM  Modules: for/r loop scans functions/**/_bp.py and emits one
REM  --hidden-import per module (functions.shared appended manually).
REM  Do NOT use --collect-submodules functions: embedded Python's
REM  python39._pth strips the project root from sys.path, so it
REM  returns an empty list at spec level (verified, broken 11.5MB exe).
REM  Data: for/d loop auto collects each package templates/static dirs.
REM  New package: add functions/name/name_bp.py with templates/static,
REM  no change to this script is needed.
REM  Note: keep this file pure ASCII. cmd batch parser misreads byte
REM  offsets after chcp 65001 when the file contains multi-byte chars.
REM ============================================================

set "consoleArgs= --hide-console hide-early"
if /i "%~1"=="--show-console" set "consoleArgs="

:: collect every functions/**/xxx_bp.py as --hidden-import
set "modArgs= --hidden-import functions.shared"
for /r functions %%f in (*_bp.py) do (
    set "rel=%%f"
    set "rel=!rel:%~dp0=!"
    set "rel=!rel:.py=!"
    set "rel=!rel:\=.!"
    set "modArgs=!modArgs! --hidden-import !rel!"
)

:: auto collect functions\pkg\{templates,static} as --add-data
set "dataArgs="
for /d %%p in (functions\*) do (
    set "pkg=%%~np"
    if exist "%%p\templates" set "dataArgs=!dataArgs! --add-data functions\!pkg!\templates;functions/!pkg!/templates"
    if exist "%%p\static"    set "dataArgs=!dataArgs! --add-data functions\!pkg!\static;functions/!pkg!/static"
)
set "dataArgs=!dataArgs! --add-data plugins;plugins"

echo Building...
.\python39\python.exe -m PyInstaller -F --noconfirm !consoleArgs! --upx-dir upx --hidden-import hosts.blueprintHost --hidden-import hosts.pluginHost !modArgs! !dataArgs! --add-binary bin\ffmpeg.exe;bin --collect-all winpty RemoteConnecter.py
echo Done: dist\RemoteConnecter.exe
