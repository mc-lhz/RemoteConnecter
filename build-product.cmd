chcp 65001
:: ============================================================
::  RemoteConnecter 构建脚本
::  PyInstaller -F -w 单文件 + templates/static 打包
:: ============================================================
echo 构建中...
pyinstaller -F -w --add-data "templates;templates" --add-data "static;static" RemoteConnecter.py
