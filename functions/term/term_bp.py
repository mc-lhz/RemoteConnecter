# -*- coding: utf-8 -*-
"""终端模块 — Windows WebSocket 终端 (ConPTY / pywinpty)

路由:
    GET  /terminal          终端页面 (纯前端, 后续可替换为首页)
    GET  /terminal/api/ws   WebSocket 终端 API (全双工, 支持多会话 + 断线重连)

仅考虑 Windows 生产环境 (pywinpty / ConPTY, 可完整还原 cmd/powershell 交互体验);
非 Windows 下回退为 subprocess 管道, 仅供本机联调, 不具备完整终端语义。

前端默认连接: ws://<host>/terminal/api/ws?cmd=cmd.exe
cmd 可为任意支持终端的程序, 例如: cmd / powershell / python 等。
可选参数 session=<id>: 命中存活会话则 attach 复用进程 (断线重连), 否则新开会话。

整合到主项目只需:
    from functions.term.term_bp import term_bp, sock
    app.register_blueprint(term_bp)
    sock.init_app(app)
"""

import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import uuid

from flask import Blueprint, jsonify, render_template, request
from flask_sock import Sock

import Logcat
Log = Logcat.Logcat()

# Windows 生产依赖: pywinpty (ConPTY)。其余平台回退为管道, 仅联调。
if sys.platform == 'win32':
    from winpty import PtyProcess
else:
    PtyProcess = None


term_bp = Blueprint('term', __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/term/static')
sock = Sock()

# 会话保活参数
DETACH_TIMEOUT = 7200   # 会话无人附着宽限期(秒), 超时杀进程回收
REAPER_INTERVAL = 10   # 回收线程扫描周期(秒)
MAX_BACKLOG = 20000    # 会话无人附着时输出队列上限(条), 超出丢最旧

REPLAY_MAX = 512 * 1024  # 回放缓冲上限(字符/字节近似), 供重连回放重建画面, 超出丢最旧

# 全局会话注册表: {sessionID: TermSession}
sessionMap = {}
sessionMapLock = threading.Lock()
reaperStarted = False   # 回收线程惰性启动标记
reaperLock = threading.Lock()


@term_bp.route('/terminal')
def terminal():
    """终端页面 — 纯静态前端, 后续可直接替换为首页"""
    return render_template('term.html')


@term_bp.route('/terminal/api/sessions')
def listSessions():
    """列出当前存活会话 (供前端刷新后恢复终端列表)。

    返回: {"sessions":[{"id":..,"cmd":..,"attached":bool}, ...]}
    仅返回 alive 的会话; 进程已退出的会话已被 _reader 移出注册表, 不在此列。
    """
    with sessionMapLock:
        snapshot = list(sessionMap.values())
    items = []
    for session in snapshot:
        with session.sessionLock:
            alive = session.alive
            attached = (session.attached is not None)
        if not alive:
            continue
        items.append({'id': session.sessionID, 'cmd': session.cmd, 'attached': attached})
    return jsonify({'sessions': items})


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
# 会话对象 (与 WS 连接解耦, 支撑保活/重连)
# ---------------------------------------------------------------------------

class TermSession:
    """终端会话: 与 WS 连接解耦, 进程在 WS 断开后继续存活 (保活)。

    一个会话同一时刻只有一个 WS 附着 (单附着, 抢占式接管)。
    进程句柄由 reader 线程创建 (pywinpty 线程亲和性), 经 self.proc 共享。
    """

    def __init__(self, sessionID, cmd, cwd):
        self.sessionID = sessionID
        self.cmd = cmd
        self.cwd = cwd
        self.proc = None            # reader 线程内创建 (spawn 与 read 必须同线程)
        self.alive = False          # spawn 成功置 True; 进程退出/启动失败置 False
        self.attached = None        # 当前附着 ws (单附着)
        self.sessionLock = threading.Lock()
        self.outQueue = queue.Queue()
        self.stop = threading.Event()
        self.spawned = threading.Event()
        self.lastDetachAt = time.time()  # 最近一次进入无人附着状态的时间戳
        self.replayBuf = []         # 输出滚动缓冲 (str/bytes 块), 供重连回放重建画面
        self.replaySize = 0         # replayBuf 近似大小 (str 计字符数, bytes 计字节数)

    def enqueueOut(self, item):
        """输出入队 + 队列封顶 + 回放缓冲维护。

        仅 _reader 线程调用: replayBuf 的 append/pop(0) 与主线程的 list() 快照
        在 CPython GIL 下均为 C 级原子操作, 无需加锁。
        先入回放缓冲再入队, 保证"快照 ⊇ 队列积压", 回放时清积压不重不丢。
        """
        kind, payload = item
        if kind == 'data':
            self.replayBuf.append(payload)
            self.replaySize += len(payload)
            while self.replaySize > REPLAY_MAX and self.replayBuf:
                removed = self.replayBuf.pop(0)
                self.replaySize -= len(removed)
        self.outQueue.put(item)
        while self.outQueue.qsize() > MAX_BACKLOG:
            try:
                self.outQueue.get_nowait()
            except queue.Empty:
                break


def newSession(cmd, cwd):
    """创建新会话: 建 TermSession -> 入注册表 -> 启动 reader 线程 -> 惰性启动回收线程。"""
    session = TermSession(uuid.uuid4().hex, cmd, cwd)
    with sessionMapLock:
        sessionMap[session.sessionID] = session
    _startReaper()
    threading.Thread(target=_reader, args=(session,), daemon=True).start()
    return session


def _removeSession(session):
    """从注册表移除会话 (幂等)。"""
    with sessionMapLock:
        sessionMap.pop(session.sessionID, None)


def _startReaper():
    """惰性启动回收线程 (全应用单例)。"""
    global reaperStarted
    with reaperLock:
        if reaperStarted:
            return
        reaperStarted = True
    threading.Thread(target=_sessionReaper, daemon=True).start()


def terminateSession(session):
    """终结会话: 停止 reader, 杀进程, 移出注册表。幂等。"""
    session.stop.set()
    with session.sessionLock:
        proc = session.proc
        session.proc = None
    if proc is not None:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.close()
        except Exception:
            pass
    session.alive = False
    _removeSession(session)
    Log.i('term', f'terminate session={session.sessionID} cmd={session.cmd}')


def _reader(session):
    """后台线程: 同线程内创建终端进程并持续读取输出 -> 入队; 不直接调用 ws.send。

    进程退出/启动失败时置 alive=False 并移出注册表, 此后重连自动降级为新开会话。
    """
    try:
        proc = spawnShell(session.cmd, session.cwd)
    except Exception as e:
        session.alive = False
        _removeSession(session)
        session.enqueueOut(('error', f'{e}'))
        Log.w('term', f'spawn failed session={session.sessionID} cmd={session.cmd} err={e}')
        return
    with session.sessionLock:
        session.proc = proc
    session.alive = True
    session.spawned.set()
    Log.i('term', f'spawn ok session={session.sessionID} cmd={session.cmd}')

    exited = False
    exitCode = None
    while not session.stop.is_set():
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
            exitCode = getattr(proc, 'exitcode', None)
            exited = True
            break
        session.enqueueOut(('data', data))

    # 进程退出 (自退或被终结): 补发 exit 帧让附着前端感知, 并注销会话
    if not exited:
        exitCode = getattr(proc, 'exitcode', None)
    session.alive = False
    session.enqueueOut(('exit', exitCode))
    _removeSession(session)
    Log.i('term', f'process exited session={session.sessionID} code={exitCode}')


def _sessionReaper():
    """回收线程: 周期性扫描, 无人附着且超过宽限期的存活会话杀进程回收。"""
    while True:
        time.sleep(REAPER_INTERVAL)
        now = time.time()
        with sessionMapLock:
            snapshot = list(sessionMap.values())
        for session in snapshot:
            with session.sessionLock:
                idle = (session.alive
                        and session.attached is None
                        and (now - session.lastDetachAt) > DETACH_TIMEOUT)
            if idle:
                Log.i('term', f'reap session={session.sessionID} idle_timeout')
                terminateSession(session)


def _detach(session, ws):
    """WS 断开: 摘除附着关系, 进程保活 (不 terminate)。仅当前附着者本人可摘除。"""
    with session.sessionLock:
        if session.attached is ws:
            session.attached = None
            session.lastDetachAt = time.time()
            Log.i('term', f'detach session={session.sessionID}')


def _sealSocketAfterClose(ws, timeout=2.0):
    """发送 close 帧并封锁 socket 写方向, 彻底阻断 werkzeug teardown 补写 HTTP 响应。

    根因 (运行时证据见 debug-ws-invalid-frame-header.md):
    flask_sock werkzeug 模式下 handler 返回普通 200 Response, werkzeug execute()
    会在返回后向已升级 socket 补写 "HTTP/1.1 200 OK" 头。浏览器完成 close 握手后
    仍处于 CLOSING 状态继续读帧 (典型于同页抢占/多客户端接管场景), 该字节被解析
    为非法帧 -> "Invalid frame header" / 1006。

    修复: 主动发 close 帧后立即 shutdown(SHUT_WR) —
      1. 浏览器依次收到 CLOSE 帧 + FIN, 干净关闭 (onclose code=1000 wasClean=true);
      2. werkzeug 的 teardown 写入必然触发 BrokenPipeError, 命中其
         connection_dropped_errors 分支被静默吞掉, 补写字节永不出网。
    """
    try:
        if getattr(ws, 'connected', False):
            try:
                ws.close()  # 发送 CLOSE 帧 (触发浏览器干净关闭)
            except Exception:
                pass  # 连接已死/状态机异常不阻塞业务
        sock = getattr(ws, 'sock', None)
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_WR)
            except OSError:
                pass  # 内部线程可能已关闭 socket
    except Exception:
        pass


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
                               {"type":"close"}  显式终止会话 (杀进程 + 移出注册表)
        后端 -> 前端  文本帧: 终端输出 (VT 序列)
                      JSON 帧: {"type":"hello","session":..,"resumed":bool,"cmd":..}
                               (attach 成功后的第一帧, 前端据此决定 reset 与否)
                               {"type":"exit","code":..} / {"type":"error","msg":..}
                               {"type":"pong"}
    """
    cmd = request.args.get('cmd') or 'cmd.exe'
    cwd = request.args.get('cwd') or os.path.expanduser('~')
    sessionID = request.args.get('session') or None

    # 命中存活会话则 attach 复用进程 (断线重连), 否则新开会话
    session = None
    resumed = False
    if sessionID:
        with sessionMapLock:
            candidate = sessionMap.get(sessionID)
        if candidate is not None and candidate.alive:
            session = candidate
            resumed = True
    if session is None:
        session = newSession(cmd, cwd)

    # 抢占式接管: 直接覆盖 attached。旧附着者不跨线程 close (规避 wsproto 线程安全),
    # 其主循环靠下面的"失权检测"自行退出。
    with session.sessionLock:
        session.attached = ws
    Log.i('term', f'attach session={session.sessionID} resumed={resumed} cmd={cmd}')

    # 等待终端进程就绪 (仅新会话需要等待; 复用会话 spawned 已 set)。
    # 未就绪前不处理输入, 避免输入在 proc 尚未创建时被丢弃。若 spawn 失败, reader 会入队 error 帧。
    if not session.spawned.wait(timeout=15):
        try:
            ws.send(json.dumps({'type': 'error', 'msg': '终端启动超时'}, ensure_ascii=False))
            ws.close()
        except Exception:
            pass
        _detach(session, ws)
        _sealSocketAfterClose(ws)
        return

    # 画面回放: 前端 fresh 恢复时带 replay=1, 先回放历史输出再接实时流, 重建
    # 画面与转义序列状态 (备用屏/鼠标模式等)。顺序保证不重不丢:
    #   ① enqueueOut 先 append replayBuf 再 put outQueue -> 积压 ⊆ 快照
    #   ② 快照后清空 outQueue 丢弃重复积压; 此后新输出只走队列, 主循环时序在回放后
    wantReplay = resumed and request.args.get('replay') == '1'
    replaySnapshot = []
    if wantReplay:
        replaySnapshot = list(session.replayBuf)
        while True:
            try:
                session.outQueue.get_nowait()
            except queue.Empty:
                break

    # hello 帧必须在主循环前发出, 保证前端 reset 决策先于任何输出。
    try:
        ws.send(json.dumps({'type': 'hello', 'session': session.sessionID,
                            'resumed': resumed, 'cmd': cmd}, ensure_ascii=False))
    except Exception:
        pass

    # 回放历史输出 (winpty 为 str, _PipeProcess 为 bytes, 需兼容解码)
    if replaySnapshot:
        for chunk in replaySnapshot:
            try:
                ws.send(chunk if isinstance(chunk, str)
                        else chunk.decode('utf-8', errors='replace'))
            except Exception:
                break

    try:
        while True:
            # 失权检测: 被抢占或会话被终结 -> 退出主循环 (保活: 不杀进程)
            with session.sessionLock:
                mine = (session.attached is ws)
            if not mine:
                break

            # 优先排空输出队列, 所有 ws.send 收敛到主线程
            while True:
                try:
                    item = session.outQueue.get_nowait()
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
                _handleControl(ws, session, payload)
                continue
            # 进程尚未就绪或已被终结则忽略本次输入
            proc = session.proc
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
        _detach(session, ws)
        # 修复 Invalid frame header: 发 close 帧并封锁写方向, 阻断 werkzeug teardown
        # 补写的 HTTP 200 被浏览器当 WebSocket 帧解析 (证据见 debug-ws-invalid-frame-header.md)
        _sealSocketAfterClose(ws)


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


def _handleControl(ws, session, payload):
    ctype = payload.get('type')
    if ctype == 'resize':
        proc = session.proc
        if proc is not None:
            try:
                proc.setwinsize(int(payload.get('rows', 24)), int(payload.get('cols', 80)))
            except Exception:
                pass
    elif ctype == 'ping':
        try:
            ws.send(json.dumps({'type': 'pong'}))
        except Exception:
            pass
    elif ctype == 'close':
        terminateSession(session)
