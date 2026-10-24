# -*- coding: utf-8 -*-
"""screen 流测试服务（8772）：仅 screen 模块"""
import os
import sys

ROOT = r'D:\desktop\py\NewProject\RC-fork-auto'
sys.path.insert(0, ROOT)

from flask import Flask
from functions.screen.screen_bp import screen_bp

app = Flask(__name__)
app.register_blueprint(screen_bp)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8772, threaded=True, use_reloader=False)
