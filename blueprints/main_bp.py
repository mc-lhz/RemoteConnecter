# -*- coding: utf-8 -*-
"""主页模块 — 首页 & 命令执行"""

import os
import platform
import subprocess

import psutil
from flask import Blueprint, render_template, request

# 创建蓝图，挂载在根路径
main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """首页 — 显示系统信息概览"""
    pc_name = platform.node()
    user_name = os.getlogin()
    hardware = platform.processor()
    os_version = platform.system() + ' ' + platform.release()

    mem = psutil.virtual_memory()
    memory = f'{mem.percent}%   可用: {mem.available}'

    disk_usage = psutil.disk_usage('/')
    disk = f'{disk_usage.percent}%   可用: {disk_usage.free}   总计: {disk_usage.total}'

    ip_list = [
        addr.address
        for interface, addrs in psutil.net_if_addrs().items()
        for addr in addrs
        if addr.family.name == 'AF_INET'
    ]
    ip_string = '\n'.join(ip_list)

    return render_template(
        'index.html',
        pcName=pc_name,
        userName=user_name,
        hardWare=hardware,
        osVersion=os_version,
        ip=ip_string,
        memory=memory,
        disk=disk,
    )


@main_bp.route('/terminal', methods=['POST'])
def execute_command():
    """执行终端命令"""
    command = request.form.get('cmd')
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    output = result.stdout if result.returncode == 0 else result.stderr
    return f'<pre>{output}</pre>'
