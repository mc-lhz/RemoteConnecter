# -*- coding: utf-8 -*-
"""蓝图宿主 — 发现并注册内置业务模块的 Blueprint/sock"""
import importlib
import pkgutil
from flask import Blueprint


def registerModuleBlueprints(app, module, sockInstances):
    """注册模块内所有 *_bp 蓝图变量, 收集 sock 实例

    约定:
        - 蓝图变量命名以 _bp 结尾 (如 main_bp = Blueprint(...))
        - WebSocket 变量固定命名 sock (如 term_bp.py 中的 sock = Sock())
    """
    for attrName, attrValue in vars(module).items():
        if attrName.endswith('_bp') and isinstance(attrValue, Blueprint):
            app.register_blueprint(attrValue)
    if hasattr(module, 'sock'):
        sockInstances.append(module.sock)


def discoverBuiltinBlueprints(app):
    """pkgutil 扫描 functions/ 下所有 *_bp 模块并注册, 返回 sock 实例列表

    注意: 必须用 pkgutil 扫描模块而非 os.listdir 扫描磁盘。
    打包后 *_bp.py 被打入 PYZ 压缩包, 磁盘上不存在对应文件,
    PyInstaller 的 pyi_rth_pkgutil 运行时钩子负责枚举 PYZ 中的模块。
    """
    import functions  # 延迟导入, 避免 import hosts 时连带加载业务模块
    sockInstances = []
    for packageInfo in pkgutil.iter_modules(functions.__path__):
        packageName = packageInfo.name
        bpPackage = importlib.import_module(f'functions.{packageName}')
        for subInfo in pkgutil.iter_modules(bpPackage.__path__):
            if not subInfo.name.endswith('_bp'):
                continue
            module = importlib.import_module(f'functions.{packageName}.{subInfo.name}')
            registerModuleBlueprints(app, module, sockInstances)
    return sockInstances


def initSockInstances(app, sockInstances):
    """所有模块注册完毕后统一 init_app (flask-sock 约定)"""
    for sockInstance in sockInstances:
        sockInstance.init_app(app)
