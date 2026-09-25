# -*- coding: utf-8 -*-
"""主页模块 — 首页 & 命令执行"""

import os
import platform
import subprocess

import psutil
from flask import Blueprint, render_template, request
from utils import *


# 创建蓝图，首页直挂根路径 /；静态资源保留 /main/static 访问路径
main_bp = Blueprint('main', __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/main/static')


@main_bp.route('/')
def index():
    """首页 — 显示系统信息概览"""
    pcName = platform.node()
    userName = os.getlogin()
    pythonVersion = getPythonVersion()
    osVersion = platform.system() + ' ' + platform.release()
    softwareVersion = getVersion()

    mem = psutil.virtual_memory()
    memory = f'{mem.percent}%   可用: {mem.available}'

    # 像 ipconfig 一样列出所有网卡及其 IPv4 地址，169删除并放到最后
    interfaceHtmlList = []
    deleteIPList = []
    for interface, addrs in psutil.net_if_addrs().items():
        ipv4List = [addr.address for addr in addrs if addr.family.name == 'AF_INET']
        if not ipv4List:
            interfaceHtmlList.append(f'{interface}: 未连接')
        else:
            for ip in ipv4List:
                # 若169开头，画删除线表示私有IP
                IPLine = f'{interface}: <a href="http://{ip}">{ip}</a>'
                if ip.startswith('169'):
                    IPLine = f'<del>{IPLine}</del>'
                    deleteIPList.append(IPLine)
                else:
                    interfaceHtmlList.append(IPLine)
    interfaceHtmlList.extend(deleteIPList)
    ipString = '<br>'.join(interfaceHtmlList)

    return render_template(
        'index.html',
        pcName=pcName,
        userName=userName,
        pythonVersion=pythonVersion,
        osVersion=osVersion,
        softwareVersion=softwareVersion,
        ip=ipString,
        memory=memory,
    )


@main_bp.route('/api/command', methods=['POST'])
def executeCommand():
    """执行终端命令"""
    command = request.form.get('cmd')
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    output = result.stdout if result.returncode == 0 else result.stderr
    return f'<pre>{output}</pre>'