# -*- coding: utf-8 -*-
"""文件模块 — 浏览、下载、上传"""

import os
import subprocess

from flask import Blueprint, jsonify, request, send_from_directory

from utils import get_available_drives, get_file_json

# 创建蓝图，挂载在 /download
file_bp = Blueprint('file', __name__)


@file_bp.route('/download')
def download_browse():
    """浏览文件系统 — 列表页"""
    path = request.args.get('path', None)

    if not path:
        drives = get_available_drives()
        html = '<h1>选择磁盘</h1><ul>'
        for drive in drives:
            html += f'<li><a href="/download?path={drive}" target="_blank">{drive}</a></li>'
        html += '</ul>'
        return html

    elif os.path.isfile(path):
        operation = request.args.get('operation', None)
        if operation == 'download':
            directory = os.path.dirname(path)
            filename = os.path.basename(path)
            return send_from_directory(os.path.abspath(directory), filename, as_attachment=True)
        elif operation == 'start':
            subprocess.run(path, check=True, shell=True)
            return '文件已启动'
        elif operation == 'delete':
            os.remove(path)
            return '文件已删除'
        else:
            return _render_file_action_dialog(path)

    elif os.path.isdir(path):
        return _render_directory_listing(path)

    else:
        return f'路径不存在: {path}'


@file_bp.route('/download/api')
def download_api():
    """文件浏览 JSON API"""
    path = request.args.get('path', None)
    return jsonify(get_file_json(path))


@file_bp.route('/upload', methods=['POST'])
def upload_file():
    """文件上传"""
    file = request.files['file']
    path = request.form.get('path', None)

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 500
    elif path == '/':
        return jsonify({'error': '禁止上传到"此电脑"'}), 500
    else:
        filename = file.filename
        try:
            file.save(os.path.join(path, filename))
            return jsonify({'filename': filename}), 200
        except Exception as e:
            return jsonify({'filename': filename, 'error': str(e)}), 500


def _render_file_action_dialog(path):
    """渲染文件操作对话框（下载/启动/删除）"""
    basename = os.path.basename(path)
    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>选择操作</title>
    <link rel="stylesheet" href="/static/jquery-ui.min.css">
    <script src="/static/jquery.js"></script>
    <script src="/static/jquery-ui.min.js"></script>
</head>
<body>
    <div id="dialog" title="选择操作">
        <p>请选择对文件 "{basename}" 的操作：</p>
    </div>
    <script>
    $(function() {{
        $("#dialog").dialog({{
            autoOpen: true,
            modal: true,
            buttons: {{
                "下载": function() {{
                    $(this).dialog("close");
                    window.location.href = String.raw`/download?path={path}&operation=download`;
                }},
                "启动": function() {{
                    $(this).dialog("close");
                    window.location.href = String.raw`/download?path={path}&operation=start`;
                }},
                "删除": function() {{
                    if (confirm("确定删除文件 {basename} 吗？")) {{
                        $(this).dialog("close");
                        window.location.href = String.raw`/download?path={path}&operation=delete`;
                    }}
                }}
            }},
            close: function() {{
                window.history.back();
            }}
        }});
    }});
    </script>
</body>
</html>'''


def _render_directory_listing(path):
    """渲染目录内容列表"""
    file_json = get_file_json(path)
    file_list = file_json['fileList']
    parent = os.path.dirname(path)

    html = f'<h1>{path}</h1>'
    html += f'<p><a href="/download?path={parent}">返回上级目录  </a><a href="/download">返回磁盘列表</a></p>'
    html += '<ul>'

    if parent and parent != path:
        html += f'<li><a href="/download?path={parent}" target="_blank">..</a></li>'

    for item in file_list:
        full_path = item['path']
        name = item['name']
        if item['type'] == 'folder':
            html += f'<li><a href="/download?path={full_path}" target="_blank" style="color:#00F;">{name}</a></li>'
        else:
            html += f'<li><a href="/download?path={full_path}" target="_blank" style="color:#F00;">{name}</a></li>'

    html += '</ul>'
    return html
