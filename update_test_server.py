# -*- coding: utf-8 -*-
"""update 模块测试服务（8774）：nodepool 全链路实测用"""
import os
import sys

ROOT = r'D:\desktop\py\NewProject\RC-fork-auto'
sys.path.insert(0, ROOT)

from flask import Flask, send_from_directory
from functions.update.update_bp import update_bp
from utils import resourcePath

app = Flask(__name__)
app.template_folder = None
app.static_folder = None


@app.route('/shared/static/<path:filename>')
def sharedStatic(filename):
    return send_from_directory(resourcePath('functions/shared/static'), filename)


app.register_blueprint(update_bp)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8774, threaded=True, use_reloader=False)