# -*- coding: utf-8 -*-
"""RemoteConnecter — 终端 (远程命令行) 功能测试入口

仅保留远程命令行 (WebSocket 终端) 功能, 用于隔离测试。
"""

import sys
import ctypes
from flask import Flask
from utils import *
from blueprints.term_bp import term_bp, sock  # 终端 (WS / ConPTY)

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
app = Flask(__name__)
app.template_folder = resourcePath('templates')
app.static_folder = resourcePath('static')

# ---- 注册蓝图 ----
app.register_blueprint(term_bp)       # 终端 (term) — 页面 /terminal + API /terminal/api/ws
sock.init_app(app)                    # 终端 WebSocket

# ---- 启动 ----
if __name__ == '__main__':
    print(getPythonVersion())
    app.run(host='0.0.0.0', port=80, debug=True, use_reloader=True)
