# -*- coding: utf-8 -*-
"""工具库 — 路径适配、环境检测、文件浏览"""

import os
import sys


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
