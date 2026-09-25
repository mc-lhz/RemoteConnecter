# -*- coding: utf-8 -*-
"""RemoteConnecter — 学校电脑管理系统 (Flask 多模块版)"""
import sys
import os
import json
import ctypes
import importlib
import importlib.util
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

    插件 (plugins/, plugin.json 清单驱动) 加载的模块也在此统一注册蓝图/sock。
    """
    sockInstances = []

    def registerModuleBlueprints(module):
        """注册模块内所有 *_bp 蓝图变量, 收集 sock 实例"""
        for attrName, attrValue in vars(module).items():
            if attrName.endswith('_bp') and isinstance(attrValue, Blueprint):
                app.register_blueprint(attrValue)
        if hasattr(module, 'sock'):
            sockInstances.append(module.sock)

    # 1) 内置业务模块: pkgutil 扫描 PYZ/源码
    for packageInfo in pkgutil.iter_modules(functions.__path__):
        packageName = packageInfo.name
        bpPackage = importlib.import_module(f'functions.{packageName}')
        for subInfo in pkgutil.iter_modules(bpPackage.__path__):
            if not subInfo.name.endswith('_bp'):
                continue
            module = importlib.import_module(f'functions.{packageName}.{subInfo.name}')
            registerModuleBlueprints(module)

    # 2) 插件: 三级目录收集加载 (磁盘实体, importlib 显式路径加载)
    for pluginModule in loadPlugins(getPluginDirs()):
        registerModuleBlueprints(pluginModule)

    for sockInstance in sockInstances:
        sockInstance.init_app(app)
# ---- 插件系统 ----
#1.获取插件目录列表 [程序级, 全局级, 用户级]
def getPluginDirs():
    """插件目录列表: [程序级, 全局级, 用户级], 越靠后优先级越高"""
    pluginDirs = []
    # 程序级: 打包态 exe 同级 / 开发态项目根
    if isPackaged():
        pluginDirs.append(os.path.join(os.path.dirname(sys.executable), 'plugins'))
    else:
        pluginDirs.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plugins'))
    # 全局级: %PROGRAMDATA%\RemoteConnecter\plugins
    programData = os.environ.get('PROGRAMDATA')
    if programData:
        if os.path.isdir(os.path.join(programData, 'RemoteConnecter', 'plugins')):
            pluginDirs.append(os.path.join(programData, 'RemoteConnecter', 'plugins'))
    # 用户级: %APPDATA%\RemoteConnecter\plugins
    appData = os.environ.get('APPDATA')
    if appData:
        if os.path.isdir(os.path.join(appData, 'RemoteConnecter', 'plugins')):
            pluginDirs.append(os.path.join(appData, 'RemoteConnecter', 'plugins'))
    Log.i('Main', f'插件目录列表: {pluginDirs}')
    return pluginDirs
#2.扫描并加载所有插件文件
# 目录结构 (每个插件一个目录 + plugin.json 清单):
# plugins/
#     pg1/
#         plugin.json      ← 清单: {"id": "pg1", "entry": "example_bp.py", "lib": "lib"(可选)}
#         example_bp.py    ← 清单 entry 指向的入口
#         lib/
#             example.pyd  ← 私有依赖 (纯 .py / 匹配 Python 3.9 win_amd64 的 .pyd)
def loadPluginFile(filepath, pluginId):
    """按显式文件路径加载插件模块, 绕过打包环境 _pth 的 import 搜索限制"""
    moduleName = 'rcplugin_' + pluginId
    moduleSpec = importlib.util.spec_from_file_location(moduleName, filepath)
    pluginModule = importlib.util.module_from_spec(moduleSpec)
    sys.modules[moduleName] = pluginModule
    moduleSpec.loader.exec_module(pluginModule)
    return pluginModule


def loadPlugins(pluginDirs):
    """扫描并加载所有插件, 返回插件模块列表 (由调用方注册蓝图/sock)

    收集阶段: 按 pluginDirs 顺序遍历, 同 id 后来者覆盖 (用户级 > 全局级 > 程序级)
    加载阶段: 每个插件 try/except 包裹, 失败仅记日志, 不阻断主程序启动
    """
    # ---- 阶段1: 收集 + 去重 ----
    # pluginIdMap: id -> (入口绝对路径, lib路径或None)
    pluginIdMap = {}
    for pluginsDir in pluginDirs:
        if not os.path.exists(pluginsDir):
            continue  # 目录不存在 (如用户从未创建) 是正常状态, 静默跳过
        if not os.path.isdir(pluginsDir):
            Log.w('插件', f'[{pluginsDir}] 存在但不是目录, 跳过')
            continue
        for pluginDirPathName in sorted(os.listdir(pluginsDir)):
            pluginDirPath = os.path.join(pluginsDir, pluginDirPathName)
            if not os.path.isdir(pluginDirPath):
                Log.w('插件', f'[{pluginDirPathName}] 不是目录, 跳过')
                continue  # plugin.json 模式只认目录插件
            manifestPath = os.path.join(pluginDirPath, 'plugin.json')
            if not os.path.isfile(manifestPath):
                Log.e('插件', f'[{pluginDirPathName}] 缺少 plugin.json, 跳过')
                continue
            try:
                # utf-8-sig 兼容带 BOM 的文件 (记事本保存 UTF-8 默认加 BOM)
                with open(manifestPath, encoding='utf-8-sig') as f:
                    manifest = json.load(f)
                pluginId = manifest['id']
                entryFile = manifest['entry']
            except (ValueError, KeyError) as e:
                Log.e('插件', f'[{pluginDirPathName}] plugin.json 无效: {e}')
                continue
            entryPath = os.path.join(pluginDirPath, entryFile)
            if not os.path.isfile(entryPath):
                Log.e('插件', f'[{pluginId}] 入口不存在: {entryFile}')
                continue
            libName = manifest.get('lib', 'lib')
            libPath = os.path.join(pluginDirPath, libName)
            libPath = libPath if os.path.isdir(libPath) else None
            pluginIdMap[pluginId] = (entryPath, libPath)

    # ---- 阶段2: 加载 ----
    pluginModules = []
    for pluginId, (pluginFilePath, libPath) in pluginIdMap.items():
        try:
            # lib/ 私有依赖入栈: 高优先级插件后处理, 先插入 sys.path 优先命中;
            # 加载后不移除, 支持插件内延迟 import
            if libPath and libPath not in sys.path:
                sys.path.insert(0, libPath)
            pluginModules.append(loadPluginFile(pluginFilePath, pluginId))
            Log.i('插件', f'已加载 [{pluginId}] {pluginFilePath}')
        except Exception as e:
            Log.e('插件', f'加载失败 [{pluginId}] {pluginFilePath}: {e}')
    return pluginModules






# ---- 启动 ----
if __name__ == '__main__':
    # 清理 _MEI 残留目录
    cleanupMeiFolders()
    # 加载插件
    try:
        discoverAndRegisterBlueprints(app)
    except Exception as e:
        Log.e('插件', f'插件宿主报错: {e}')
    Log.i('Main', getPythonVersion())
    app.run(host='0.0.0.0', port=80, debug=True, use_reloader=True)
