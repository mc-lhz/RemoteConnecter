# -*- coding: utf-8 -*-
#Flask项目，实现文件远程下载
#允许下载整个D盘
import os
import sys
import subprocess
import platform,psutil
from flask import Flask, send_from_directory, request, render_template, send_file, jsonify
from PIL import ImageGrab
import io
import threading

# PyInstaller 打包后资源路径适配
def resource_path(relative_path):
    """获取资源的绝对路径，兼容 PyInstaller 打包"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

app = Flask(__name__)
app.template_folder = resource_path('templates')
app.static_folder = resource_path('static')

def get_available_drives():
    drives = []
    for drive in range(ord('A'), ord('Z')+1):
        drive_name = chr(drive) + ":\\"
        if os.path.exists(drive_name):
            drives.append(drive_name)

    return drives

def get_file_json(path):
    fileJson = {}
    parent = os.path.dirname(path)
    if path == r"/":
        fileJson["parentPath"] = r"/"
        fileJson["currentPath"] = r"/"
        fileJson["fileList"] = [{"type":"folder","path":drive} for drive in get_available_drives()]
    else:
        if parent and parent == path:
            fileJson["parentPath"] = r"/"
        else:
            fileJson["parentPath"] = parent
        fileJson["currentPath"] = path
        fileJson["fileList"] = get_file_list(path)
    return fileJson

def get_file_list(path):
    fileList = []
    items = os.listdir(path)
    
    for item in items:
        fullPath = os.path.join(path, item)
        if os.path.isdir(fullPath):
            fileList.append({"type": "folder", "path": fullPath, "name": item.lower()})
        elif os.path.isfile(fullPath):
            fileList.append({"type": "file", "path": fullPath, "name": item.lower()})
    
    # 排序：文件夹优先，然后按名称排序
    def sort_key(x):
        # 文件夹排在前面，名称按字母排序
        return (0 if x["type"] == "folder" else 1, x["name"])
    
    fileList.sort(key=sort_key)
    return fileList

@app.route('/terminal', methods=['POST'])
def execute_command():
    command = request.form.get('cmd')
    # 使用 subprocess 执行命令
    result = subprocess.run(
        command, 
        shell=True,
        capture_output=True,
        text=True
    )
    output = result.stdout if result.returncode == 0 else result.stderr
    return f"<pre>{output}</pre>"
        
@app.route('/')
def index():
    
    pcName = platform.node()
    userName = os.getlogin()
    hardWare = platform.processor()
    osVersion = platform.system() + " " + platform.release()
    memory = str(psutil.virtual_memory().percent) + "% " + str(psutil.virtual_memory().available)
    disk = str(psutil.disk_usage('/').percent) + "% " + str(psutil.disk_usage('/').free) +" "+ str(psutil.disk_usage('/').total)
    ipList = [addr.address for interface, addrs in psutil.net_if_addrs().items() for addr in addrs if addr.family.name == "AF_INET"]
    ipString = "\n".join(ipList)
    
    return render_template('index.html',pcName=pcName,userName=userName, hardWare=hardWare, osVersion=osVersion, ip=ipString, memory=memory, disk=disk)  
    
@app.route('/screenshot')
def get_screenshot():
    if request.args.get('getimage', None) == 'true':
        screenshot = ImageGrab.grab()
        img_io = io.BytesIO()      # 内存中的字节流
        screenshot.save(img_io, 'PNG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/png')   # 直接返回给客户端
    else:
        return render_template('screenshot.html')

# 浏览和下载文件
@app.route('/download')
def download_browse():
    path = request.args.get('path', None)
    
    if not path:
        # 如果没有路径参数，显示磁盘列表
        drives = get_available_drives()
        html = "<h1>选择磁盘</h1>"
        html += "<ul>"
        for drive in drives:
            html += f'<li><a href="/download?path={drive}" target="_blank">{drive}</a></li>'
        html += "</ul>"
        return html
    
    # 如果路径是文件
    elif os.path.isfile(path):
        userOperation = request.args.get('operation', None)
        if userOperation == 'download':
            directory = os.path.dirname(path)
            filename = os.path.basename(path)
            directory = os.path.abspath(directory)
            return send_from_directory(directory, filename, as_attachment=True)
        elif userOperation == 'start':
            # threading.Thread()
            subprocess.run(path, check=True, shell=True)
            return "文件已启动"
        elif userOperation == 'delete':
            os.remove(path)
            return "文件已删除"
        else:
            html = rf'''
<!DOCTYPE html>
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
        <p>请选择对文件 "{os.path.basename(path)}" 的操作：</p>
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
                    if (confirm("确定删除文件 {os.path.basename(path)} 吗？")) {{
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
</html>
'''
            return html
    # 如果路径是目录，显示内容
    elif os.path.isdir(path):
        fileJson = get_file_json(path)
        fileList = fileJson["fileList"]
        parent = fileJson["parentPath"]
        html = f"<h1>{path}</h1>"
        
        parent = os.path.dirname(path)
        
        html += f'<p><a href="/download?path={parent}">返回上级目录  </a><a href="/download">返回磁盘列表</a></p>'
        html += "<ul>"
        
        # 添加上级目录链接（如果不是根目录）
        
        if parent and parent != path:
            html += f'<li><a href="/download?path={parent}" target="_blank">..</a></li>'
        
        for item in fileList:
            if item["type"] == "folder":
                fullPath = item["path"]
                name = item["name"]
                html += f'<li><a href="/download?path={fullPath}" target="_blank" style="color: #0000FF;">{name}</a></li>'
            elif item["type"] == "file":
                fullPath = item["path"]
                name = item["name"]
                html += f'<li><a href="/download?path={fullPath}" target="_blank" style="color: #FF0000;">{name}</a></li>'
            
            
            
        
        html += "</ul>"
        return html
    else:
        return f"路径不存在: {path}"
@app.route('/download/api')
def download_api():
    path = request.args.get('path', None)
    
    fileJson = get_file_json(path)
    return jsonify(fileJson)



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80,debug=True,use_reloader=False)
