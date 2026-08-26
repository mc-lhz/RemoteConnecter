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
    from functions.term.term_bp import term_bp, sock
    app.register_blueprint(term_bp)
    sock.init_app(app)
"""

import json
import os
import queue
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


term_bp = Blueprint('term', __name__,
    template_folder='templates',
    static_folder='static',
    url_prefix='/term')
sock = Sock()


@term_bp.route('/terminal')
def terminal():
    """终端页面 — 纯静态前端, 后续可直接替换为首页"""
    return render_template('term.html')


# ---------------------------------------------------------------------------
# 进程启动
# ---------------------------------------------------------------------------

def spawnShell(cmd, cwd):
    """启动终端程序。Windows 用 ConPTY; 其它平台用管道回退(仅联调)。"""
    if sys.platform == 'win32' and PtyProcess is not None:
        return _spawnWindows(cmd, cwd)
    return _PipeProcess(cmd, cwd, {**os.environ, 'TERM': 'xterm-256color'})


def _spawnWindows(cmd, cwd):
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
def wsTerminal(ws):
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

    # 进程对象由 reader 线程内部创建 (spawn 与 read 必须在同一线程,
    # 否则 pywinpty 的阻塞 read() 在异线程调用会立即抛 EOFError('Pty is closed'))
    procRef = {'proc': None, 'err': None}
    spawned = threading.Event()
    outQueue = queue.Queue()
    stop = threading.Event()

    def reader():
        """后台线程: 同线程内创建终端进程并持续读取输出 -> 入队; 不直接调用 ws.send"""
        try:
            proc = spawnShell(cmd, cwd)
        except Exception as e:
            procRef['err'] = e
            outQueue.put(('error', f'{e}'))
            return
        procRef['proc'] = proc
        spawned.set()
        while not stop.is_set():
            try:
                data = proc.read()
            except Exception:
                # pywinpty 在 pty 关闭时抛 EOFError -> 进程已退出; 其它读异常同样视为结束
                break
            if data is None:
                # 非 Windows 回退(_PipeProcess): 当前暂无输出, 继续轮询
                continue
            if isinstance(data, str) and data == '':
                # pywinpty 内部的 b'0011Ignore 哨兵帧会被转换为空串返回,
                # 这是"忽略帧"而非 EOF, 必须丢弃, 否则会被误判为进程退出。
                continue
            if isinstance(data, bytes) and not data:
                # 非 Windows 回退(_PipeProcess): 空 bytes 才是真正的 EOF
                outQueue.put(('exit', getattr(proc, 'exitcode', None)))
                break
            outQueue.put(('data', data))

    threading.Thread(target=reader, daemon=True).start()

    # 等待终端进程就绪 (spawn 在 reader 线程内完成); 未就绪前不处理输入,
    # 避免输入在 proc 尚未创建时被丢弃。若 spawn 失败, reader 会入队 error 帧。
    if not spawned.wait(timeout=15):
        try:
            ws.send(json.dumps(
                {'type': 'error', 'msg': '终端启动超时'}, ensure_ascii=False))
            ws.close()
        except Exception:
            pass
        return

    # 主线程轮询: 统一在此发送输出(避免多线程并发 ws.send 破坏 wsproto 状态机),
    # 并接收客户端输入帧。proc 由 reader 线程创建, 经 procRef 共享。
    try:
        while True:
            # 优先排空输出队列, 所有 ws.send 收敛到主线程
            while True:
                try:
                    item = outQueue.get_nowait()
                except queue.Empty:
                    break
                kind, payload = item
                if kind == 'error':
                    try:
                        ws.send(json.dumps(
                            {'type': 'error', 'msg': f'启动失败: {payload}'}, ensure_ascii=False))
                        ws.close()
                    except Exception:
                        pass
                    return
                if kind == 'exit':
                    try:
                        ws.send(json.dumps(
                            {'type': 'exit', 'code': payload}, ensure_ascii=False))
                        ws.close()
                    except Exception:
                        pass
                    return
                # proc.read() 在 Windows(pywinpty) 返回 str, 在非 Windows(_PipeProcess) 返回 bytes,
                # 需兼容两者: str 直接发送, bytes 先解码。
                text = payload if isinstance(payload, str) else payload.decode('utf-8', errors='replace')
                try:
                    ws.send(text)
                except Exception:
                    return

            # 带超时接收客户端帧, 实现输出转发与输入处理的轮询
            try:
                msg = ws.receive(timeout=0.05)
            except Exception:
                break
            if msg is None:
                continue
            payload, isCtrl = _decodeFrame(msg)
            if isCtrl:
                _handleControl(ws, procRef.get('proc'), payload)
                continue
            # 进程尚未就绪则忽略本次输入
            proc = procRef.get('proc')
            if proc is None:
                continue
            # pywinpty(Windows) 的 write 接受 str; 非 Windows 回退(_PipeProcess) 接受 bytes
            if sys.platform == 'win32':
                # Windows 控制台约定: 回车用 CR; 粘贴里的 LF 统一转为 CR
                data = payload.replace('\r\n', '\r').replace('\n', '\r')
            else:
                data = payload.encode('utf-8')
            try:
                proc.write(data)
            except Exception:
                break
    except Exception:
        pass
    finally:
        stop.set()
        proc = procRef.get('proc')
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.close()
            except Exception:
                pass


def _decodeFrame(msg):
    """区分控制帧(带 type 键的 JSON)与原始输入。返回 (payload, isControl)"""
    text = msg if isinstance(msg, str) else msg.decode('utf-8', errors='replace')
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and 'type' in obj:
            return obj, True
    except (ValueError, TypeError):
        pass
    return text, False


def _handleControl(ws, proc, payload):
    ctype = payload.get('type')
    if ctype == 'resize':
        try:
            proc.setwinsize(int(payload.get('rows', 24)), int(payload.get('cols', 80)))
        except Exception:
            pass
    elif ctype == 'ping':
        ws.send(json.dumps({'type': 'pong'}))
