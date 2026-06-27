# -*- coding: utf-8 -*-
"""RemoteConnecter — 学校电脑管理系统 (Flask 多模块版)"""
import sys
import ctypes
from flask import Flask
from utils import get_python_version, is_packaged, resource_path
from blueprints.main_bp import main_bp
from blueprints.file_bp import file_bp
from blueprints.screen_bp import screen_bp
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
app.template_folder = resource_path('templates')
app.static_folder = resource_path('static')

# ---- 注册蓝图 ----
app.register_blueprint(main_bp)       # 主页 & 终端
app.register_blueprint(file_bp)       # 文件浏览 / 下载 / 上传
app.register_blueprint(screen_bp)     # 屏幕截图 / 推流 / 远程控制

# ---- 启动 ----
if __name__ == '__main__':
    print(get_python_version())
    print(is_packaged())
    app.run(host='0.0.0.0', port=80, debug=True, use_reloader=False)
