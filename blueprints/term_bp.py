# -*- coding: utf-8 -*-
"""终端模块 — Windows WebSocket 终端 (ConPTY / pywinpty)

路由:
    GET  /terminal          终端页面 (纯前端, 后续可替换为首页)
    GET  /terminal/api/ws   WebSocket 终端 API (全双工)

仅考虑 Windows 生产环境 (pywinpty / ConPTY, 可完整还原 cmd/powershell 交互体验);
非 Windows 下回退为 subprocess 管道, 仅供本机联调, 不具备完整终端语义。

前端默认连接: ws://<host>/terminal/api/ws?cmd=cmd.exe
cmd 可为任意支持终端的程序, 例如: cmd / powershell / python 等。

整合到主项目只需:
    from blueprints.term_bp import term_bp, sock
    app.register_blueprint(term_bp)
    sock.init_app(app)
"""

import json
import os
import subprocess
import sys
import threading

from flask import Blueprint, render_template, request
from flask_sock import Sock

# Windows 生产依赖: pywinpty (ConPTY)。其余平台回退为管道, 仅联调。
if sys.platform == 'win32':
    from winpty import PtyProcess
else:
    PtyProcess = None


term_bp = Blueprint('term', __name__)
sock = Sock()


@term_bp.route('/terminal')
def terminal():
    """终端页面 — 纯静态前端, 后续可直接替换为首页"""
    return render_template('term.html')


# ---------------------------------------------------------------------------
# 进程启动
# ---------------------------------------------------------------------------

def spawn_shell(cmd, cwd):
    """启动终端程序。Windows 用 ConPTY; 其它平台用管道回退(仅联调)。"""
    if sys.platform == 'win32' and PtyProcess is not None:
        return _spawn_windows(cmd, cwd)
    return _PipeProcess(cmd, cwd, {**os.environ, 'TERM': 'xterm-256color'})


def _spawn_windows(cmd, cwd):
    """Windows: 通过 ConPTY(pywinpty) 启动任意终端程序, 还原完整控制台语义"""
    return PtyProcess.spawn(
        cmd,
        cwd=cwd,
        env={**os.environ, 'TERM': 'xterm-256color'},
        dimensions=(24, 80),
    )


class _PipeProcess:
    """非 Windows 联调回退: subprocess 管道, 无 TTY 语义 (仅供开发测试)。

    read() 约定: None=暂无输出; b''=进程已退出/EOF; bytes=输出块。
    """

    def __init__(self, cmd, cwd, env):
        argv = cmd.split() if isinstance(cmd, str) else cmd
        self._proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, cwd=cwd, env=env, bufsize=0,
        )

    def read(self):
        import select
        r, _, _ = select.select([self._proc.stdout], [], [], 0.2)
        if not r:
            return None
        try:
            data = self._proc.stdout.read1(4096)
        except Exception:
            try:
                data = os.read(self._proc.stdout.fileno(), 4096)
            except Exception:
                return b''
        return data

    def write(self, data):
        if self._proc.poll() is None:
            self._proc.stdin.write(data)
            self._proc.stdin.flush()

    def setwinsize(self, rows, cols):
        pass

    def terminate(self, force=True):
        if self._proc.poll() is None:
            self._proc.kill()

    def close(self):
        if self._proc.poll() is None:
            self._proc.kill()

    @property
    def exitcode(self):
        return self._proc.poll()


# ---------------------------------------------------------------------------
# WebSocket 终端
# ---------------------------------------------------------------------------

@sock.route('/terminal/api/ws', bp=term_bp)
def ws_terminal(ws):
    """WebSocket 终端: 前端输入 -> 进程 stdin; 进程 stdout -> 前端。

    帧协议:
        前端 -> 后端  文本帧: 原始按键/粘贴输入 (UTF-8)
                      JSON 帧: 控制帧 {"type":"resize","cols":..,"rows":..}
                               {"type":"ping"}
        后端 -> 前端  文本帧: 终端输出 (VT 序列)
                      JSON 帧: {"type":"exit","code":..} / {"type":"error","msg":..}
    """
    cmd = request.args.get('cmd') or 'cmd.exe'
    cwd = request.args.get('cwd') or os.path.expanduser('~')

    try:
        proc = spawn_shell(cmd, cwd)
    except Exception as e:
        ws.send(json.dumps({'type': 'error', 'msg': f'启动失败: {e}'}, ensure_ascii=False))
        return

    stop = threading.Event()

    def reader():
        """后台线程: 读进程输出 -> ws.send"""
        while not stop.is_set():
            try:
                data = proc.read()
            except Exception:
                break
            if data is None:
                continue
            if not data:
                # 进程退出 / EOF
                try:
                    ws.send(json.dumps(
                        {'type': 'exit', 'code': getattr(proc, 'exitcode', None)},
                        ensure_ascii=False))
                    ws.close()
                except Exception:
                    pass
                break
            try:
                ws.send(data.decode('utf-8', errors='replace'))
            except Exception:
                break

    threading.Thread(target=reader, daemon=True).start()

    try:
        while True:
            msg = ws.receive()
            if msg is None:
                break
            payload, is_ctrl = _decode_frame(msg)
            if is_ctrl:
                _handle_control(ws, proc, payload)
                continue
            data = payload.encode('utf-8')
            # Windows 控制台约定: 回车用 CR; 粘贴里的 LF 统一转为 CR
            if sys.platform == 'win32':
                data = data.replace(b'\r\n', b'\r').replace(b'\n', b'\r')
            try:
                proc.write(data)
            except Exception:
                break
    except Exception:
        pass
    finally:
        stop.set()
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.close()
        except Exception:
            pass


def _decode_frame(msg):
    """区分控制帧(带 type 键的 JSON)与原始输入。返回 (payload, is_control)"""
    text = msg if isinstance(msg, str) else msg.decode('utf-8', errors='replace')
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and 'type' in obj:
            return obj, True
    except (ValueError, TypeError):
        pass
    return text, False


def _handle_control(ws, proc, payload):
    ctype = payload.get('type')
    if ctype == 'resize':
        try:
            proc.setwinsize(int(payload.get('rows', 24)), int(payload.get('cols', 80)))
        except Exception:
            pass
    elif ctype == 'ping':
        ws.send(json.dumps({'type': 'pong'}))
