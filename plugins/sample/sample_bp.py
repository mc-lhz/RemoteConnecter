# -*- coding: utf-8 -*-
"""sample 插件 — 最小示例"""
import json
import os

from flask import Blueprint, jsonify, render_template

# 获取插件id (以 __file__ 锚定, 不依赖运行时 CWD)
pluginDir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(pluginDir, 'plugin.json'), encoding='utf-8-sig') as f:
    pluginID = json.load(f)['id']

# 蓝图注册名 = 插件id, 保证多插件蓝图名/endpoint/路由不冲突
# (变量名 sample_bp 只需以 _bp 结尾供宿主发现, 跨插件不冲突)
sample_bp = Blueprint(f'{pluginID}_bp', __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path=f'/{pluginID}/static')


@sample_bp.route(f'/{pluginID}')
def sample():
    return render_template('sample.html', pluginID=pluginID)
    
@sample_bp.route(f'/{pluginID}/sample')
def sample_json():
    return jsonify({'message': 'sample'})
