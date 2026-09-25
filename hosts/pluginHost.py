# -*- coding: utf-8 -*-
"""插件宿主 — 四级目录收集加载 plugin.json 清单驱动的插件"""
import sys
import os
import json
import importlib.util

import Logcat
Log = Logcat.Logcat()

from utils import resourcePath, isPackaged
from hosts.blueprintHost import registerModuleBlueprints


def getPluginDirs():
    """插件目录列表: [自带插件，程序级, 全局级, 用户级], 越靠后优先级越高"""
    pluginDirs = []
    # 自带插件: 开发态程序级目录下/打包态_MEI临时文件夹下的 plugins 子目录
    pluginDirs.append(resourcePath('plugins'))
    # 程序级: 打包态 exe 同级
    if isPackaged():
        pluginDirs.append(os.path.join(os.path.dirname(sys.executable), 'plugins'))
    # 全局级: %PROGRAMDATA%\RemoteConnecter\plugins
    programData = os.environ.get('PROGRAMDATA')
    if programData:
        pluginDirs.append(os.path.join(programData, 'RemoteConnecter', 'plugins'))
    # 用户级: %APPDATA%\RemoteConnecter\plugins
    appData = os.environ.get('APPDATA')
    if appData:
        pluginDirs.append(os.path.join(appData, 'RemoteConnecter', 'plugins'))
    # 删除不存在的目录
    pluginDirs = [d for d in pluginDirs if os.path.exists(d) and os.path.isdir(d)]
    Log.i('Main', f'插件目录列表: {pluginDirs}')
    return pluginDirs


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

    目录结构 (每个插件一个目录 + plugin.json 清单):
        plugins/
            pg1/
                plugin.json      <- 清单: {"id": "pg1", "entry": "example_bp.py", "lib": "lib"(可选)}
                example_bp.py    <- 清单 entry 指向的入口
                lib/
                    example.pyd  <- 私有依赖 (纯 .py / 匹配 Python 3.9 win_amd64 的 .pyd)
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


def loadAndRegisterPlugins(app):
    """四级目录收集 -> 加载 -> 注册蓝图; 返回 sock 列表 (交给 initSockInstances)"""
    sockInstances = []
    for pluginModule in loadPlugins(getPluginDirs()):
        registerModuleBlueprints(app, pluginModule, sockInstances)
    return sockInstances
