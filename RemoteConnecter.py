# -*- coding: utf-8 -*-
"""RemoteConnecter — 学校电脑管理系统 (Flask 多模块版)"""
import sys
import ctypes
from flask import Flask
import Logcat
Log = Logcat.Logcat()

from utils import *
from hosts.blueprintHost import discoverBuiltinBlueprints, initSockInstances
from hosts.pluginHost import loadAndRegisterPlugins

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


# ---- 启动 ----
if __name__ == '__main__':
    # 清理 _MEI 残留目录
    cleanupMeiFolders()
    # 宿主初始化: 内置模块 + 插件, 统一注册蓝图并挂载 WebSocket
    try:
        sockInstances = discoverBuiltinBlueprints(app)
        sockInstances += loadAndRegisterPlugins(app)
        initSockInstances(app, sockInstances)
    except Exception as e:
        Log.e('宿主', f'宿主初始化报错: {e}')
    Log.i('Main', getPythonVersion())
    # threaded=True 必须: 多会话架构要求并发处理多个连接/请求
    # (sessionMap 是进程内内存表, winpty 句柄不可跨进程共享, 故不能用 processes>1)。
    # 注: 此前的 "Invalid frame header" 并非线程数问题, 真因是 werkzeug teardown
    # 在 handler 返回后向已升级 socket 补写 HTTP 200 响应头, 已由
    # functions/term/term_bp.py 的 _sealSocketAfterClose (SHUT_WR 封锁) 修复。
    app.run(host='0.0.0.0', port=80, debug=True, use_reloader=True, threaded=True)
