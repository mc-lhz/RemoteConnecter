# -*- coding: utf-8 -*-
"""工具库 — 路径适配、环境检测、文件浏览、自动更新"""
# 新电脑推送测试
import os
import sys
import subprocess
import tempfile
import requests


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


def update(update_url):
    """
    检查更新并执行自动更新（无脚本版本）
    
    Args:
        update_url: 更新文件下载地址
        
    Returns:
        bool: 是否成功触发更新（函数返回后程序将退出）
    """
    # 检查是否在打包环境下
    if not is_packaged():
        return False,"请在打包环境下运行更新"
    
    try:
        import requests
        
        # 获取 temp 目录和主程序路径
        temp_dir = tempfile.gettempdir()
        updater_path = os.path.join(temp_dir, 'Updater.exe')
        main_exe = sys.executable
        
        print(f'[更新] 正在下载: {update_url}')
        try:
            response = requests.get(update_url, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f'[更新] 下载失败: {e}')
            return False,e
        
        with open(updater_path, 'wb') as f:
            f.write(response.content)
        
        print(f'[更新] 下载完成: {updater_path}')
        
        # 直接执行命令（无脚本）
        # 延迟命令 -> 复制文件 -> 启动程序 -> 删除自身
        cmd = (
            f'ping 127.0.0.1 -n 2 >nul & '
            f'ping 127.0.0.1 -n 2 >nul & '
            f'copy /Y "{updater_path}" "{main_exe}" & '
            f'start "" "{main_exe}" & '
            f'del "{updater_path}"'
        )
        
        print('[更新] 启动更新进程')
        
        # 静默启动（不显示窗口）
        subprocess.Popen(
            cmd,
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            cwd=temp_dir
        )
        
        return True,"更新成功"
        
    except Exception as e:
        print(f'[更新] 失败: {e}')
        return False,e,"更新失败"
