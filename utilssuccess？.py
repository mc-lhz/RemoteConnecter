# -*- coding: utf-8 -*-
"""工具库 — 路径适配、环境检测、文件浏览、自动更新"""
import os
import sys
import subprocess
import tempfile
import requests
import re
from urllib.parse import urlparse
import tempfile

VERSION = 'v1.1'

def get_version():
    return VERSION


def resource_path(relative_path):
    """获取资源的绝对路径，兼容 PyInstaller 打包"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


def is_packaged():
    """是否在 PyInstaller 打包环境中运行"""
    return hasattr(sys, '_MEIPASS') or getattr(sys, 'frozen', False)


def get_python_version():
    """获取 Python 版本字符串"""
    return sys.version


def get_available_drives():
    """获取系统中所有可用驱动器盘符"""
    drives = []
    for drive in range(ord('A'), ord('Z') + 1):
        drive_name = chr(drive) + ':\\'
        if os.path.exists(drive_name):
            drives.append(drive_name)
    return drives


def get_file_list(path):
    """获取指定路径下的文件和文件夹列表（已排序）"""
    file_list = []
    try:
        items = os.listdir(path)
    except PermissionError:
        return file_list

    for item in items:
        full_path = os.path.join(path, item)
        if os.path.isdir(full_path):
            file_list.append({'type': 'folder', 'path': full_path, 'name': item.lower()})
        elif os.path.isfile(full_path):
            file_list.append({'type': 'file', 'path': full_path, 'name': item.lower()})

    file_list.sort(key=lambda x: (0 if x['type'] == 'folder' else 1, x['name']))
    return file_list


def get_file_json(path):
    """构建文件浏览的 JSON 结构（含父路径、当前路径、文件列表）"""
    file_json = {}
    parent = os.path.dirname(path)

    if path == '/':
        file_json['parentPath'] = '/'
        file_json['currentPath'] = '/'
        file_json['fileList'] = [
            {'type': 'folder', 'path': drive} for drive in get_available_drives()
        ]
    else:
        file_json['parentPath'] = '/' if (parent and parent == path) else parent
        file_json['currentPath'] = path
        file_json['fileList'] = get_file_list(path)

    return file_json

def get_filename_from_header(response):
    cd = response.headers.get('Content-Disposition')
    if cd:
        match = re.search(r'filename="?([^"]+)"?', cd)
        if match:
            return match.group(1)
    return None

def remote_download(url, save_dir):
    # 下载文件, stream=True 用于大文件下载

    response = requests.get(url, timeout=10, stream=True, verify=False,  proxies={'http': None, 'https': None})
    response.raise_for_status()
    # 保存文件
    # 优先从响应头获取文件名
    filename = get_filename_from_header(response)
    # 如果响应头没有文件名，从 URL 提取文件名
    if not filename:
        filename = os.path.basename(urlparse(url).path)
    # 构建保存路径
    save_path = os.path.join(save_dir, filename)
    try:
        with open(save_path, 'wb') as f:
            f.write(response.content)
            return True, save_path
    except Exception as e:
        return False, str(e)


def update(update_url):
    """
    检查更新并执行自动更新（无脚本版本）
    
    Args:
        update_url: 更新文件下载地址
        
    Returns:
        tuple: (success: bool, message: str)
    """
    testDownload = False
    if not update_url:
        return False, "更新地址不能为空"
    
    if not is_packaged():
        # return False, "请在打包环境下运行更新"
        # 启用测试更新模式
        testDownload = True
    
    try:
        import requests
        temp_dir = tempfile.gettempdir()
        updater_path = os.path.join(temp_dir, 'RemoteConnecterUpdater.exe')
        main_exe = sys.executable
        
        print(f'[更新] 正在下载: {update_url}')
        try:
            response = requests.get(update_url, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f'[更新] 下载失败: {e}')
            return False, f"下载失败: {str(e)}"
        
        with open(updater_path, 'wb') as f:
            f.write(response.content)
        
        print(f'[更新] 下载完成: {updater_path}')
        # 启动更新
        if not testDownload:
            batch_path = os.path.join(temp_dir, 'RemoteConnecterUpdate.bat')
            log_path = os.path.join(temp_dir, 'RemoteConnecterUpdate.log')
            exe_dir = os.path.dirname(main_exe)
            with open(batch_path, 'w', encoding='utf-8') as f:
                f.write(f'''@echo off
chcp 65001 >nul
set "log={log_path}"
echo [%date% %time%] update started >> "%log%"
echo pid={os.getpid()} >> "%log%"
echo updater={updater_path} >> "%log%"
echo target={main_exe} >> "%log%"

:wait
tasklist /FI "PID eq {os.getpid()}" 2>nul | find /i "{os.getpid()}" >nul
if not errorlevel 1 (
    echo [%time%] waiting for old process... >> "%log%"
    ping 127.0.0.1 -n 3 >nul
    goto wait
)
echo [%time%] old process exited >> "%log%"

ping 127.0.0.1 -n 4 >nul

echo [%time%] copying... >> "%log%"
copy /Y "{updater_path}" "{main_exe}" >> "%log%" 2>&1
if errorlevel 1 (
    echo [%time%] copy failed, retrying... >> "%log%"
    ping 127.0.0.1 -n 6 >nul
    copy /Y "{updater_path}" "{main_exe}" >> "%log%" 2>&1
)
echo [%time%] copy exit code: %errorlevel% >> "%log%"

echo [%time%] starting new exe... >> "%log%"
cd /d "{exe_dir}"
start "" "{main_exe}"
echo [%time%] start done, errorlevel=%errorlevel% >> "%log%"

del "%~f0"
''')

            print(f'[更新] 启动更新脚本: {batch_path}')

            subprocess.Popen(
                ['cmd.exe', '/c', batch_path],
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            )
        else:
            print('[更新] 开发环境，仅下载')
            return True, "开发环境，仅下载"
    except Exception as e:
        print(f'[更新] 更新失败: {e}')
        return False, f"更新失败: {str(e)}"