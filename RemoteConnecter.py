# -*- coding: utf-8 -*-
"""RemoteConnecter — 学校电脑管理系统 (Flask 多模块版)"""
import sys
import os
import ctypes
import importlib
import pkgutil
from flask import Flask, Blueprint
import Logcat
Log = Logcat.Logcat()

from utils import *
import functions
# ---- Windows DPI 感知设置 (必须在最开始设置) ----
if sys.platform == 'win32':
    try:
        # 设置 DPI 感知级别为 Per Monitor DPI Aware V2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            # 回退到系统级 DPI 感知
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# ---- 创建应用 ----
# 各蓝图自带 template_folder/static_folder，主应用无需全局指定
app = Flask(__name__)
app.template_folder = None
app.static_folder = None


# ---- 公共静态资源 (shared/static, 多个蓝图共享) ----
@app.route('/shared/static/<path:filename>')
def sharedStatic(filename):
    from flask import send_from_directory
    return send_from_directory(resourcePath('functions/shared/static'), filename)


# ---- 注册蓝图 (自动扫描 functions/ 下所有 *_bp.py) ----
def discoverAndRegisterBlueprints(app):
    """自动发现 functions/ 下所有业务包中的蓝图并注册

    约定:
        - 业务包目录位于 functions/ 下, 每个包内至少一个 *_bp.py 模块
        - 蓝图变量命名以 _bp 结尾 (如 main_bp = Blueprint(...))
        - WebSocket 变量固定命名 sock (如 term_bp.py 中的 sock = Sock())
    新功能只需在 functions/ 下新建业务包 + *_bp.py, 无需改动主入口。

    注意: 必须用 pkgutil 扫描模块而非 os.listdir 扫描磁盘。
    打包后 *_bp.py 被打入 PYZ 压缩包, 磁盘上不存在对应文件,
    PyInstaller 的 pyi_rth_pkgutil 运行时钩子负责枚举 PYZ 中的模块。
    """
    sockInstances = []
    for packageInfo in pkgutil.iter_modules(functions.__path__):
        packageName = packageInfo.name
        bpPackage = importlib.import_module(f'functions.{packageName}')
        for subInfo in pkgutil.iter_modules(bpPackage.__path__):
            if not subInfo.name.endswith('_bp'):
                continue
            module = importlib.import_module(f'functions.{packageName}.{subInfo.name}')
            for attrName, attrValue in vars(module).items():
                if attrName.endswith('_bp') and isinstance(attrValue, Blueprint):
                    app.register_blueprint(attrValue)
            if hasattr(module, 'sock'):
                sockInstances.append(module.sock)
    for sockInstance in sockInstances:
        sockInstance.init_app(app)


discoverAndRegisterBlueprints(app)
# ---- 启动 ----

if __name__ == '__main__':
    # 清理 _MEI 残留目录
    cleanupMeiFolders()
    Log.i('Main', getPythonVersion())
    app.run(host='0.0.0.0', port=80, debug=True, use_reloader=True)
