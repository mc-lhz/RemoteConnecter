# -*- coding: utf-8 -*-
"""Process 插件 — 远程进程查看与终止。

路由:
    GET  /process              管理页面
    GET  /process/api/list     进程列表（CPU/内存排序，支持过滤）
    POST /process/api/kill     终止进程（带自保护与 PID 复用校验）
"""

import json
import os

import psutil
from flask import Blueprint, jsonify, render_template, request

pluginDir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(pluginDir, 'plugin.json'), encoding='utf-8-sig') as manifestFile:
    pluginID = json.load(manifestFile)['id']

process_bp = Blueprint(
    '{}_bp'.format(pluginID),
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/{}/static'.format(pluginID),
)

MAX_PROCESSES = 500

# Windows 关键系统进程，终止会直接蓝屏/失联，硬拒绝
_CRITICAL_NAMES = {
    'system', 'system idle process', 'registry', 'smss.exe', 'csrss.exe',
    'wininit.exe', 'winlogon.exe', 'services.exe', 'lsass.exe',
}


@process_bp.after_request
def _noStore(response):
    if request.path.startswith('/{}/api/'.format(pluginID)):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@process_bp.route('/{}'.format(pluginID))
def processPage():
    return render_template('process.html', pluginID=pluginID)


@process_bp.route('/{}/api/list'.format(pluginID))
def apiList():
    query = (request.args.get('query') or '').strip().lower()
    procs = []
    selfPid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'memory_percent', 'status', 'username']):
        try:
            info = proc.info
            name = info.get('name') or ''
            pid = info.get('pid')
            if query and query not in name.lower() and query not in str(pid):
                continue
            try:
                # 归一化到单核百分比（与任务管理器一致）；首次调用返回 0，
                # process_iter 内部复用实例，自动刷新下第二次起有值
                cpu = round(proc.cpu_percent(interval=None) / (psutil.cpu_count() or 1), 1)
            except psutil.Error:
                cpu = 0.0
            procs.append({
                'pid': pid,
                'name': name,
                'cpu': cpu,
                'mem': round(info.get('memory_percent') or 0.0, 1),
                'status': info.get('status') or '',
                'user': info.get('username') or '',
                'self': pid == selfPid,
            })
        except (psutil.Error, KeyError, TypeError):
            continue
    procs.sort(key=lambda item: (-item['mem'], -item['cpu'], item['name'].lower()))
    return jsonify({
        'processes': procs[:MAX_PROCESSES],
        'total': len(procs),
        'truncated': len(procs) > MAX_PROCESSES,
    })


@process_bp.route('/{}/api/kill'.format(pluginID), methods=['POST'])
def apiKill():
    payload = request.get_json(silent=True) or {}
    try:
        pid = int(payload.get('pid'))
    except (TypeError, ValueError):
        return jsonify({'error': '无效的 PID'}), 400
    if pid == os.getpid():
        return jsonify({'error': '不能终止本程序自身'}), 400
    if pid == os.getppid():
        return jsonify({'error': '不能终止父进程'}), 400

    try:
        target = psutil.Process(pid)
        name = target.name()
    except psutil.NoSuchProcess:
        return jsonify({'error': '进程不存在（可能已退出）'}), 404
    except psutil.AccessDenied:
        return jsonify({'error': '没有权限访问该进程'}), 403

    # PID 复用校验：前端提交时的名称与当前不一致则拒绝
    expected = payload.get('name')
    if expected and expected != name:
        return jsonify({'error': '进程已变化（当前为 {}），已拒绝终止'.format(name)}), 409
    if name.lower() in _CRITICAL_NAMES:
        return jsonify({'error': '系统关键进程，已拒绝终止'}), 400

    try:
        target.terminate()
        _, alive = psutil.wait_procs([target], timeout=2)
        if alive:
            target.kill()
            _, alive = psutil.wait_procs([target], timeout=2)
            if alive:
                return jsonify({'error': '终止失败（可能需要更高权限）'}), 500
    except psutil.AccessDenied:
        return jsonify({'error': '没有权限终止该进程'}), 403
    except psutil.NoSuchProcess:
        pass  # 竞态：刚好已退出
    return jsonify({'ok': True, 'pid': pid, 'name': name})
