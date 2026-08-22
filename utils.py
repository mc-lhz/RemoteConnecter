# -*- coding: utf-8 -*-

# 软件版本号
VERSION = 'v1.4.1'

"""工具库 — 路径适配、环境检测、文件浏览、自动更新"""

import os
import sys
import subprocess
import tempfile
import re
import threading, time
from urllib.parse import urlparse
import requests
import Logcat

Log = Logcat.Logcat()

def getVersion():
    return VERSION


def resourcePath(relativePath):
    """获取资源的绝对路径，兼容 PyInstaller 打包"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relativePath)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relativePath)


def isPackaged():
    """是否在 PyInstaller 打包环境中运行"""
    return hasattr(sys, '_MEIPASS') or getattr(sys, 'frozen', False)


def getPythonVersion():
    """获取 Python 版本字符串"""
    return sys.version


def getAvailableDrives():
    """获取系统中所有可用驱动器盘符"""
    drives = []
    for drive in range(ord('A'), ord('Z') + 1):
        driveName = chr(drive) + ':\\'
        if os.path.exists(driveName):
            drives.append(driveName)
    return drives


def getFileList(path):
    """获取指定路径下的文件和文件夹列表（已排序）"""
    fileList = []
    try:
        items = os.listdir(path)
    except PermissionError:
        return fileList

    for item in items:
        fullPath = os.path.join(path, item)
        if os.path.isdir(fullPath):
            fileList.append({'type': 'folder', 'path': fullPath, 'name': item.lower()})
        elif os.path.isfile(fullPath):
            fileList.append({'type': 'file', 'path': fullPath, 'name': item.lower()})

    fileList.sort(key=lambda x: (0 if x['type'] == 'folder' else 1, x['name']))
    return fileList


def getFileJson(path):
    """构建文件浏览的 JSON 结构（含父路径、当前路径、文件列表）"""
    fileJson = {}
    parent = os.path.dirname(path)

    if path == '/':
        fileJson['parentPath'] = '/'
        fileJson['currentPath'] = '/'
        fileJson['fileList'] = [
            {'type': 'folder', 'path': drive} for drive in getAvailableDrives()
        ]
    else:
        fileJson['parentPath'] = '/' if (parent and parent == path) else parent
        fileJson['currentPath'] = path
        fileJson['fileList'] = getFileList(path)

    return fileJson


def getFilenameFromHeader(response):
    cd = response.headers.get('Content-Disposition')
    if cd:
        match = re.search(r'filename="?([^"]+)"?', cd)
        if match:
            return match.group(1)
    return None


def remoteDownload(url, saveDir):
    # 下载文件, stream=True 用于大文件下载
    response = requests.get(url, timeout=10, stream=True, verify=False, proxies={'http': None, 'https': None})
    response.raise_for_status()
    # 保存文件
    # 优先从响应头获取文件名
    fileName = getFilenameFromHeader(response)
    # 如果响应头没有文件名，从 URL 提取文件名
    if not fileName:
        fileName = os.path.basename(urlparse(url).path)
    # 构建保存路径
    savePath = os.path.join(saveDir, fileName)
    try:
        with open(savePath, 'wb') as f:
            f.write(response.content)
            return True, savePath
    except Exception as e:
        return False, str(e)


# ===== 全局变量定义 =====
TEMP_DIR = tempfile.gettempdir()
UPDATER_FILE_NAME = 'RemoteConnecterUpdater.exe'
UPDATE_BAT_NAME = 'RemoteConnecterUpdate.bat'
UPDATE_LOG_NAME = 'RemoteConnecterUpdate.log'
UPDATER_PATH = os.path.join(TEMP_DIR, UPDATER_FILE_NAME)


def startUpdate(updaterPath, mainExe, testDownload=False):
    """
    使用exe更新
    Args:
        updaterPath: 更新包路径
        mainExe: 主程序路径
        testDownload: 是否测试模式（默认False）
    Returns:
        tuple: (success: bool, message: str)
    """
    if not testDownload:
        batchPath = os.path.join(TEMP_DIR, UPDATE_BAT_NAME)
        logPath = os.path.join(TEMP_DIR, UPDATE_LOG_NAME)
        with open(batchPath, 'w', encoding='utf-8') as f:
            f.write(f'''@echo off
:: ================================================
::  RemoteConnecter 自动更新脚本
::  流程：等待旧进程退出 -> 复制新文件 -> 启动新进程 -> 自删除
:: ================================================

chcp 65001 >nul
set "log={logPath}"

:: 记录更新开始信息
echo [%date% %time%] update started >> "%log%"
echo pid={os.getpid()} >> "%log%"
echo updater={updaterPath} >> "%log%"
echo target={mainExe} >> "%log%"

:: ================================================
:: 阶段1：等待旧进程退出（确保文件可被覆盖）
:: ================================================
:wait
tasklist /FI "PID eq {os.getpid()}" /NH 2>nul | findstr "{os.getpid()}" >nul
if not errorlevel 1 (
    echo [%time%] waiting for old process... >> "%log%"
    ping 127.0.0.1 -n 3 >nul
    goto wait
)
echo [%time%] old process exited >> "%log%"

ping 127.0.0.1 -n 4 >nul

:: ================================================
:: 阶段2：复制更新包到目标位置
:: ================================================
echo [%time%] copying... >> "%log%"
copy /Y "{updaterPath}" "{mainExe}" >> "%log%" 2>&1
if errorlevel 1 (
    echo [%time%] copy failed, retrying... >> "%log%"
    ping 127.0.0.1 -n 6 >nul
    copy /Y "{updaterPath}" "{mainExe}" >> "%log%" 2>&1
)
echo [%time%] copy exit code: %errorlevel% >> "%log%"

:: ================================================
:: 阶段4：启动新程序（explorer.exe = ShellExecute = 等效双击）
:: ================================================
echo [%time%] starting new exe... >> "%log%"
explorer.exe "{mainExe}"
echo [%time%] start done, errorlevel=%errorlevel% >> "%log%"

ping 127.0.0.1 -n 2 >nul
del "%~f0"
''')

        Log.i('更新', f'启动更新脚本: {batchPath}')

        subprocess.Popen(
            f'start /b "" "{batchPath}"',
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            cwd=TEMP_DIR,
        )

        return True, "更新成功"

    else:
        Log.i('更新', '开发环境，仅下载')
        return True, "开发环境，仅下载"


def localUpdate(updaterFileObject, mainExe=None, testDownload=None):
    """
    本地更新
    Args:
        updaterFileObject: 更新包文件对象
        mainExe: 主程序路径（默认使用 sys.executable）
        testDownload: 是否测试模式（None=自动判断打包环境）
    Returns:
        tuple: (success: bool, message: str)
    """
    if mainExe is None:
        mainExe = sys.executable
    if testDownload is None:
        testDownload = not isPackaged()
    updaterFileObject.save(UPDATER_PATH)
    updateResult = startUpdate(UPDATER_PATH, mainExe, testDownload)
    return updateResult


def remoteUpdate(updateUrl):
    """
    检查更新并执行自动更新（无脚本版本）

    Args:
        updateUrl: 更新文件下载地址

    Returns:
        tuple: (success: bool, message: str)
    """
    testDownload = False
    mainExe = sys.executable
    if not updateUrl:
        return False, "更新地址不能为空"

    if not isPackaged():
        testDownload = True

    try:
        Log.i('更新', f'正在下载: {updateUrl}')
        try:
            response = requests.get(updateUrl, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            Log.e('更新', f'下载失败: {e}')
            return False, f"下载失败: {str(e)}"

        with open(UPDATER_PATH, 'wb') as f:
            f.write(response.content)

        Log.i('更新', f'下载完成: {UPDATER_PATH}')
        updateResult = startUpdate(UPDATER_PATH, mainExe, testDownload)
        return updateResult
    except Exception as e:
        Log.e('更新', f'失败: {e}')
        return False, f"更新失败: {str(e)}"



if __name__ == '__main__':
    pass