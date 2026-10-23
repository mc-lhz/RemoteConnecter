# -*- coding: utf-8 -*-
"""系统面板 — 硬件状态 / 快动作 / 电源 / 进程窗口应用管理"""

import csv
import ctypes
import io
import os
import subprocess
import threading
import time

from flask import Blueprint, jsonify, render_template, request

import Logcat

Log = Logcat.Logcat()
from utils import resourcePath

pluginID = 'monitor'
monitor_bp = Blueprint(
    f'{pluginID}_bp',
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path=f'/{pluginID}/static',
)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

KILL_BLACKLIST = {
    'system', 'idle', 'registry', 'memory compression', 'memcompression',
    'smss.exe', 'csrss.exe', 'wininit.exe', 'winlogon.exe',
    'services.exe', 'lsass.exe', 'fontdrvhost.exe',
}

_cpuLock = threading.Lock()
_lastCpuSample = None


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [('cbSize', ctypes.c_uint), ('dwTime', ctypes.c_uint)]


def _cpuPercent():
    global _lastCpuSample
    with _cpuLock:
        idle = ctypes.c_ulonglong()
        kernel = ctypes.c_ulonglong()
        user = ctypes.c_ulonglong()
        kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
        sample = (idle.value, kernel.value, user.value, time.time())
        if _lastCpuSample is None:
            time.sleep(0.25)
            idle2 = ctypes.c_ulonglong()
            kernel2 = ctypes.c_ulonglong()
            user2 = ctypes.c_ulonglong()
            kernel32.GetSystemTimes(ctypes.byref(idle2), ctypes.byref(kernel2), ctypes.byref(user2))
            sample2 = (idle2.value, kernel2.value, user2.value, time.time())
        else:
            sample2 = sample
            sample = _lastCpuSample
        _lastCpuSample = sample2
        dTotal = (sample2[1] - sample[1]) + (sample2[2] - sample[2])
        dIdle = sample2[0] - sample[0]
        if dTotal <= 0:
            return 0.0
        return round(max(0.0, min(100.0, (1.0 - dIdle / dTotal) * 100.0)), 1)


def _memoryInfo():
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
            ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
            ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
            ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
            ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
        ]
    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    return {
        'percent': stat.dwMemoryLoad,
        'total': stat.ullTotalPhys,
        'free': stat.ullAvailPhys,
    }


def _disks():
    buf = ctypes.create_unicode_buffer(512)
    copied = kernel32.GetLogicalDriveStringsW(511, buf)
    drives = []
    for drive in ctypes.wstring_at(buf, copied).split('\x00'):
        if not drive:
            continue
        free = ctypes.c_ulonglong()
        total = ctypes.c_ulonglong()
        ok = kernel32.GetDiskFreeSpaceExW(
            ctypes.c_wchar_p(drive), ctypes.byref(free), ctypes.byref(total), None)
        if ok and total.value > 0:
            drives.append({'drive': drive, 'free': free.value, 'total': total.value})
    return drives


def _uptimeSeconds():
    return int(kernel32.GetTickCount64() / 1000)


def formatBytes(num):
    value = float(num)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024 or unit == 'TB':
            return f'{value:.1f} {unit}' if unit != 'B' else f'{int(value)} B'
        value /= 1024
    return f'{value:.1f} TB'


@monitor_bp.route(f'/{pluginID}')
def monitorPage():
    return render_template('monitor.html', pluginID=pluginID)


@monitor_bp.route(f'/{pluginID}/api/stats')
def apiStats():
    try:
        import utils as utilsModule
        version = getattr(utilsModule, 'VERSION', '')
    except Exception:
        version = ''
    mem = _memoryInfo()
    userName = os.environ.get('USERNAME', '')
    hostName = os.environ.get('COMPUTERNAME', '')
    idleSeconds = None
    try:
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if user32.GetLastInputInfo(ctypes.byref(info)):
            idleSeconds = int((kernel32.GetTickCount() - info.dwTime) / 1000)
    except Exception:
        pass
    return jsonify({
        'host': f'{hostName}\\{userName}',
        'uptimeSeconds': _uptimeSeconds(),
        'cpuPercent': _cpuPercent(),
        'memory': mem,
        'disks': _disks(),
        'idleSeconds': idleSeconds,
        'version': version,
    })


@monitor_bp.route(f'/{pluginID}/api/overview')
def apiOverview():
    pills = [{'name': '屏幕', 'state': '正常', 'detail': ''}]
    sessionCount = None
    try:
        from functions.term import term_bp
        with term_bp.sessionMapLock:
            sessionCount = sum(1 for s in term_bp.sessionMap.values() if s.alive)
    except Exception as exc:
        Log.w('monitor', f'term session probe failed: {exc}')
    if sessionCount is None:
        pills.append({'name': '终端', 'state': '未知', 'detail': ''})
    else:
        pills.append({'name': '终端', 'state': '正常', 'detail': str(sessionCount)})
    try:
        import utils as utilsModule
        version = getattr(utilsModule, 'VERSION', '')
    except Exception:
        version = ''
    return jsonify({'pills': pills, 'version': version})


def _keyTap(vk):
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, 2, 0)


ACTIONS = {
    'volume_up': lambda: _keyTap(0xAF),
    'volume_down': lambda: _keyTap(0xAE),
    'volume_mute': lambda: _keyTap(0xAD),
    'media_play': lambda: _keyTap(0xB3),
    'lock': lambda: user32.LockWorkStation(),
    'monitor_off': lambda: user32.SendMessageTimeoutW(
        0xFFFF, 0x0112, 0xF170, 2, 0x0002, 1000, None),
}


@monitor_bp.route(f'/{pluginID}/api/action', methods=['POST'])
def apiAction():
    body = request.get_json(silent=True) or {}
    action = str(body.get('type', '')).strip()
    if action in ACTIONS:
        try:
            ACTIONS[action]()
            return jsonify({'ok': True, 'message': f'已执行 .{action}'})
        except Exception as exc:
            return jsonify({'ok': False, 'message': f'{action} 失败: {exc}'}), 500
    if action == 'sleep':
        subprocess.Popen(['rundll32.exe', 'powrprof.dll,SetSuspendState', '0,1,0'])
        return jsonify({'ok': True, 'message': '已执行 .sleep'})
    if action in ('restart', 'shutdown'):
        flag = '/r' if action == 'restart' else '/s'
        subprocess.Popen(['shutdown', flag, '/t', '5'])
        hint = '5 秒后重启，远程连接将中断' if action == 'restart' else '5 秒后关机，远程连接将中断'
        return jsonify({'ok': True, 'message': hint})
    return jsonify({'ok': False, 'message': f'未知操作: {action}'}), 400


def _processRows():
    proc = subprocess.run(
        ['tasklist', '/fo', 'csv', '/nh'],
        capture_output=True, timeout=30)
    text = proc.stdout.decode('gbk', 'replace')
    rows = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 5:
            continue
        name = row[0].strip()
        try:
            pid = int(row[1])
            memK = int(row[4].replace(',', '').replace(' K', '').replace('K', '').strip() or 0)
        except ValueError:
            continue
        rows.append({'name': name, 'pid': pid, 'mem': memK * 1024})
    return rows


@monitor_bp.route(f'/{pluginID}/api/processes')
def apiProcesses():
    query = (request.args.get('q') or '').strip().lower()
    groups = {}
    for row in _processRows():
        item = groups.setdefault(row['name'], {'name': row['name'], 'count': 0, 'mem': 0, 'pids': []})
        item['count'] += 1
        item['mem'] += row['mem']
        item['pids'].append({'pid': row['pid'], 'mem': row['mem']})
    items = [groups[k] for k in groups if not query or query in k.lower()]
    items.sort(key=lambda x: x['mem'], reverse=True)
    total = sum(i['mem'] for i in items)
    return jsonify({'items': items[:200], 'total': len(items), 'totalMem': total})


@monitor_bp.route(f'/{pluginID}/api/kill', methods=['POST'])
def apiKill():
    body = request.get_json(silent=True) or {}
    pid = body.get('pid')
    name = str(body.get('name') or '').strip()
    if pid is not None:
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'message': 'pid 无效'}), 400
        if pid <= 4:
            return jsonify({'ok': False, 'message': '拒绝结束系统进程'}), 400
        proc = subprocess.run(['taskkill', '/PID', str(pid), '/F'], capture_output=True)
        ok = proc.returncode == 0
        detail = proc.stdout.decode('gbk', 'replace').strip() or proc.stderr.decode('gbk', 'replace').strip()
        return jsonify({'ok': ok, 'message': (f'已结束 PID {pid}' if ok else detail or '结束失败')})
    if not name:
        return jsonify({'ok': False, 'message': '缺少 pid 或 name'}), 400
    if name.lower() in KILL_BLACKLIST:
        return jsonify({'ok': False, 'message': f'{name} 是系统关键进程，已拒绝'}), 403
    proc = subprocess.run(['taskkill', '/IM', name, '/F'], capture_output=True)
    ok = proc.returncode == 0
    detail = proc.stdout.decode('gbk', 'replace').strip() or proc.stderr.decode('gbk', 'replace').strip()
    return jsonify({'ok': ok, 'message': (f'已结束 {name}' if ok else detail or '结束失败')})


def _exeNameOf(pid):
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ''
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = ctypes.c_ulong(512)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return ''
    finally:
        kernel32.CloseHandle(handle)


@monitor_bp.route(f'/{pluginID}/api/windows')
def apiWindows():
    result = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                result.append({
                    'hwnd': int(hwnd) if hwnd else 0,
                    'title': buf.value,
                    'pid': pid.value,
                    'exe': _exeNameOf(pid.value),
                })
        return True

    user32.EnumWindows(callback, None)
    return jsonify({'items': result[:300]})


@monitor_bp.route(f'/{pluginID}/api/window', methods=['POST'])
def apiWindow():
    body = request.get_json(silent=True) or {}
    try:
        hwnd = int(body.get('hwnd'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'message': 'hwnd 无效'}), 400
    op = str(body.get('op') or '')
    SW_MINIMIZE, SW_MAXIMIZE = 6, 3
    try:
        if op == 'close':
            user32.PostMessageW(hwnd, 0x0010, 0, 0)
        elif op == 'min':
            user32.ShowWindowAsync(hwnd, SW_MINIMIZE)
        elif op == 'max':
            user32.ShowWindowAsync(hwnd, SW_MAXIMIZE)
        elif op == 'focus':
            user32.SetForegroundWindow(hwnd)
        else:
            return jsonify({'ok': False, 'message': f'未知操作: {op}'}), 400
        return jsonify({'ok': True, 'message': f'已执行 .window_{op}'})
    except Exception as exc:
        return jsonify({'ok': False, 'message': str(exc)}), 500


def _startMenuDirs():
    dirs = []
    programData = os.environ.get('PROGRAMDATA', r'C:\ProgramData')
    appData = os.environ.get('APPDATA', '')
    dirs.append(os.path.join(programData, r'Microsoft\Windows\Start Menu\Programs'))
    if appData:
        dirs.append(os.path.join(appData, r'Microsoft\Windows\Start Menu\Programs'))
    return [d for d in dirs if os.path.isdir(d)]


@monitor_bp.route(f'/{pluginID}/api/apps')
def apiApps():
    items = {}
    for base in _startMenuDirs():
        for root, dirs, files in os.walk(base):
            depth = os.path.relpath(root, base).count(os.sep)
            if depth >= 2:
                dirs[:] = []
                continue
            for file in files:
                if not file.lower().endswith('.lnk'):
                    continue
                name = os.path.splitext(file)[0]
                path = os.path.join(root, file)
                if name not in items:
                    items[name] = {'name': name, 'path': path}
    ordered = sorted(items.values(), key=lambda x: x['name'].lower())
    return jsonify({'items': ordered[:400]})


@monitor_bp.route(f'/{pluginID}/api/open-app', methods=['POST'])
def apiOpenApp():
    body = request.get_json(silent=True) or {}
    path = str(body.get('path') or '')
    if not path.lower().endswith('.lnk') or not os.path.isfile(path):
        return jsonify({'ok': False, 'message': '应用不存在'}), 404
    allowed = False
    for base in _startMenuDirs():
        if os.path.normcase(path).startswith(os.path.normcase(base)):
            allowed = True
            break
    if not allowed:
        return jsonify({'ok': False, 'message': '路径不在开始菜单内'}), 403
    os.startfile(path)
    return jsonify({'ok': True, 'message': '已启动应用'})
