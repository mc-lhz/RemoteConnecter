// 远程终端前端: 多会话 + 侧边栏 + 断线重连 + 心跳保活
// 每会话一个 xterm 实例; 仅前台会话持有 WebSocket, 后台会话切换时断开 WS (服务端保活, 进程不杀)。

// 常量
const PING_INTERVAL = 15000;    // 心跳间隔(ms), 保 NAT/中间设备链路
const RECONNECT_BASE = 1000;    // 重连退避基数(ms)
const RECONNECT_MAX = 30000;    // 重连退避封顶(ms)
const KEYS_PREF_KEY = 'showControlKeys';
const SIDEBAR_PREF_KEY = 'sidebarOpen';
const URL_CWD = new URLSearchParams(location.search).get('cwd') || '';

// 会话状态
let sessions = [];              // 全部会话
let activeSession = null;       // 当前前台会话 (仅此会话持有 ws)
let uidCounter = 0;

// DOM 引用
const statusEl = document.getElementById('status');
const btn = document.getElementById('connect');
const controlKeys = document.getElementById('control-keys');
const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebar-toggle');
const sidebarOverlay = document.getElementById('sidebar-overlay');

function setStatus(text, cls) {
    statusEl.textContent = text;
    statusEl.className = cls || '';
}

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
}

function stateText(s) {
    switch (s.state) {
        case 'connecting': return '连接中';
        case 'connected': return '已连接';
        case 'reconnecting': return '重连中 ' + (s.retryCount || 0);
        case 'detached': return '已断开';
        case 'ended': return '已退出';
        default: return s.state || '-';
    }
}

// ---------------------------------------------------------------------------
// 会话创建 / 切换 / 关闭
// ---------------------------------------------------------------------------

// 构建会话 xterm UI + 会话对象 (不连接、不入列、不切前台)
// 供 createSession (新建) 与 restoreSessions (刷新恢复) 复用
function buildSessionUI(cmd, existingSessionID) {
    const command = (cmd || '').trim() || 'cmd.exe';
    const termHost = document.getElementById('terminal');
    const container = document.createElement('div');
    container.className = 'session-terminal';
    termHost.appendChild(container);

    const term = new Terminal({
        cursorBlink: true,
        fontFamily: 'Consolas, "Courier New", monospace',
        fontSize: 14,
        theme: {
            background: '#0d1117',
            foreground: '#c9d1d9',
            cursor: '#58a6ff',
            selectionBackground: '#264f78'
        }
    });
    const fit = new FitAddon.FitAddon();
    term.loadAddon(fit);
    term.open(container);

    const session = {
        uid: 's' + (++uidCounter),
        sessionID: existingSessionID || null,   // 服务端会话 id; 恢复时预填, 否则 hello 帧后填入
        cmd: command,
        term: term,
        fit: fit,
        el: container,
        ws: null,
        state: 'connecting',
        retryCount: 0,
        retryTimer: null,
        pingTimer: null,
        manualClose: false,
        needReplay: false     // 一次性: fresh 空终端首次连接时向服务端请求画面回放, hello 后消费
    };

    // 键盘输入只发给"本会话且本会话为前台"时的 ws
    term.onData(function (d) {
        if (session === activeSession && session.ws && session.ws.readyState === 1) {
            session.ws.send(d);
        }
    });
    term.onResize(function () {
        sendResizeFor(session);
    });
    return session;
}

// 新建终端会话: 建 UI -> 入列 -> 切前台
function createSession(cmd) {
    const session = buildSessionUI(cmd);
    sessions.push(session);
    switchSession(session);
}

function createSessionFromInput() {
    const input = document.getElementById('cmd');
    createSession(input ? input.value : '');
}

function switchSession(session) {
    if (!session) { return; }
    const prev = activeSession;
    if (prev && prev !== session) {
        // 旧前台断开 WS (服务端保活, 进程不杀), 抑制其自动重连
        clearTimers(prev);
        prev.manualClose = true;
        if (prev.ws && prev.ws.readyState <= 1) {
            try { prev.ws.close(); } catch (err) { /* ignore */ }
        }
        prev.ws = null;
        prev.state = 'detached';
    }
    activeSession = session;
    sessions.forEach(function (s) { s.el.hidden = (s !== session); });
    session.manualClose = false;
    renderSidebar();
    if (session.state === 'ended') {
        // 已退出/错误会话: 不重连, 仅展示定格画面
        setStatus('已退出: ' + session.cmd, 'err');
        return;
    }
    try { session.fit.fit(); } catch (err) { /* ignore */ }
    connectWs(session);
}

function closeSession(session) {
    // 通知服务端终止会话 (杀进程 + 移出注册表)
    if (session.ws && session.ws.readyState === 1) {
        try { session.ws.send(JSON.stringify({ type: 'close' })); } catch (err) { /* ignore */ }
    }
    clearTimers(session);
    session.manualClose = true;
    if (session.ws) {
        try { session.ws.close(); } catch (err) { /* ignore */ }
        session.ws = null;
    }
    try { session.term.dispose(); } catch (err) { /* ignore */ }
    if (session.el && session.el.parentNode) {
        session.el.parentNode.removeChild(session.el);
    }
    const idx = sessions.indexOf(session);
    if (idx >= 0) { sessions.splice(idx, 1); }
    if (activeSession === session) {
        activeSession = sessions.length ? sessions[sessions.length - 1] : null;
        if (activeSession) {
            switchSession(activeSession);
        } else {
            setStatus('未连接');
        }
    }
    renderSidebar();
}

// 页面加载时拉取服务端存活会话列表, 重建终端列表并重连恢复
// (断线重连由 onclose 处理; 此处专门处理整页刷新: 前端 sessions 清空, 需向服务端重新询问)
function restoreSessions() {
    fetch('/terminal/api/sessions')
        .then(function (res) { return res.json(); })
        .then(function (data) {
            const items = (data && data.sessions) || [];
            if (!items.length) { return; }
            items.forEach(function (it) {
                const s = buildSessionUI(it.cmd, it.id);
                s.needReplay = true;   // fresh 空终端: 首次连接请求服务端回放历史画面
                sessions.push(s);
            });
            // 优先恢复未被其他客户端附着的第一条, 其余保持 detached (后台保活, 切前台时重连)
            const first = items.find(function (it) { return !it.attached; }) || items[0];
            const target = sessions.find(function (s) { return s.sessionID === first.id; });
            if (target) { switchSession(target); }
            renderSidebar();
        })
        .catch(function () { /* 拉取失败 (如服务未就绪) 静默, 用户可手动新建 */ });
}

// ---------------------------------------------------------------------------
// WebSocket 连接 / 重连
// ---------------------------------------------------------------------------

function clearTimers(session) {
    if (session.pingTimer) { clearInterval(session.pingTimer); session.pingTimer = null; }
    if (session.retryTimer) { clearTimeout(session.retryTimer); session.retryTimer = null; }
}

function connectWs(session) {
    // 防抢占: 同一会话已有存活/半关闭连接时禁止重复建连
    // (否则服务端对旧连接失权退出, 旧连接浏览器侧报 1006/Invalid frame header;
    //  典型触发: 侧边栏重复点击已激活会话、快速连点"新建")
    if (session.ws && session.ws.readyState <= 2) { return; }
    clearTimers(session);
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    let url = proto + '://' + location.host + '/terminal/api/ws?cmd=' + encodeURIComponent(session.cmd);
    if (session.sessionID) { url += '&session=' + encodeURIComponent(session.sessionID); }
    if (session.needReplay) { url += '&replay=1'; }
    if (URL_CWD && !session.sessionID) { url += '&cwd=' + encodeURIComponent(URL_CWD); }
    if (session.state !== 'reconnecting') { session.state = 'connecting'; }
    setStatus(session.state === 'reconnecting' ? '重连中: ' + session.cmd : '连接中: ' + session.cmd);

    const socket = new WebSocket(url);
    session.ws = socket;

    socket.onopen = function () {
        session.retryCount = 0;
        // 15s 心跳 ping 保 NAT 链路 (后端回 pong)
        session.pingTimer = setInterval(function () {
            if (socket.readyState === 1) { socket.send(JSON.stringify({ type: 'ping' })); }
        }, PING_INTERVAL);
        // reset 与否由 hello 帧的 resumed 字段决定 (见 onmessage), 此处不重置
    };

    socket.onmessage = function (e) {
        let obj = null;
        try { obj = JSON.parse(e.data); } catch (err) { obj = null; }
        if (obj && obj.type) {
            handleControl(session, socket, obj);
        } else {
            // 解析失败 = 原始 VT 输出 -> 直接渲染
            session.term.write(e.data);
        }
    };

    socket.onclose = function (e) {
        if (session.ws !== socket) { return; }   // 已被新连接取代, 忽略过期关闭
        session.ws = null;
        clearTimers(session);
        if (session.state === 'ended') {
            // exit/error 已在 handleControl 处理过状态
            renderSidebar();
            return;
        }
        if (session.manualClose) {
            // 主动断开 (切换/关闭): 服务端保活, 不重连
            renderSidebar();
            return;
        }
        setStatus('连接断开 (code ' + e.code + ')', 'err');
        scheduleReconnect(session);
    };

    socket.onerror = function () {
        if (session.ws === socket) { setStatus('连接出错', 'err'); }
    };
}

function handleControl(session, socket, obj) {
    if (obj.type === 'hello') {
        session.sessionID = obj.session;
        session.needReplay = false;   // 一次性消费: 同页后续重连不再请求回放 (避免画面重复)
        if (obj.resumed === false) {
            session.term.reset();   // 新进程: 清空; resumed=true 时保留画面 (现场恢复)
        }
        session.state = 'connected';
        setStatus('已连接: ' + (obj.cmd || session.cmd), 'ok');
        try { session.fit.fit(); } catch (err) { /* ignore */ }
        sendResizeFor(session);
        renderSidebar();
        return;
    }
    if (obj.type === 'exit') {
        session.term.write('\r\n\x1b[90m[进程已退出 code=' + (obj.code === null ? '?' : obj.code) + ']\x1b[0m\r\n');
        session.state = 'ended';
        clearTimers(session);
        setStatus('已退出: ' + session.cmd, 'err');
        try { socket.close(); } catch (err) { /* ignore */ }
        renderSidebar();
        return;
    }
    if (obj.type === 'error') {
        session.term.write('\r\n\x1b[31m[错误] ' + obj.msg + '\x1b[0m\r\n');
        session.state = 'ended';
        clearTimers(session);
        setStatus('错误: ' + obj.msg, 'err');
        try { socket.close(); } catch (err) { /* ignore */ }
        renderSidebar();
        return;
    }
    // pong: 忽略
}

function scheduleReconnect(session) {
    // 仅前台会话重连 (后台会话无 ws, 切回时由 switchSession->connectWs 自然恢复)
    if (session !== activeSession) { return; }
    session.retryCount += 1;
    session.state = 'reconnecting';
    const delay = Math.min(RECONNECT_BASE * Math.pow(2, session.retryCount - 1), RECONNECT_MAX);
    setStatus('重连中 (第 ' + session.retryCount + ' 次)', 'err');
    renderSidebar();
    session.retryTimer = setTimeout(function () {
        session.retryTimer = null;
        connectWs(session);
    }, delay);
}

// ---------------------------------------------------------------------------
// 尺寸同步 / 控制键 (作用于前台会话)
// ---------------------------------------------------------------------------

function sendResizeFor(session) {
    if (session && session.ws && session.ws.readyState === 1) {
        session.ws.send(JSON.stringify({ type: 'resize', cols: session.term.cols, rows: session.term.rows }));
    }
}

function sendResize() {
    if (activeSession) { sendResizeFor(activeSession); }
}

// 发送控制键序列 (ESC, Ctrl+C, 方向键, Tab 等)
// 发送原始 VT 序列, 后端 _decodeFrame 会自动回落到 PTY write 路径
function sendControlKey(seq) {
    if (activeSession && activeSession.ws && activeSession.ws.readyState === 1) {
        activeSession.ws.send(seq);
    }
}

// ---------------------------------------------------------------------------
// 侧边栏渲染
// ---------------------------------------------------------------------------

function renderSidebar() {
    const list = document.getElementById('session-list');
    if (!list) { return; }
    list.innerHTML = '';
    sessions.forEach(function (s) {
        const li = document.createElement('li');
        li.className = 'session-item' + (s === activeSession ? ' active' : '');
        li.innerHTML =
            '<span class="session-name">' + escapeHtml(s.cmd) + '</span>' +
            '<span class="session-state">' + stateText(s) + '</span>' +
            '<button class="session-close" title="关闭终端">&times;</button>';
        li.addEventListener('click', function () { switchSession(s); });
        li.querySelector('.session-close').addEventListener('click', function (e) {
            e.stopPropagation();
            closeSession(s);
        });
        list.appendChild(li);
    });
}

// ---------------------------------------------------------------------------
// 全局事件绑定
// ---------------------------------------------------------------------------

// "新建" 按钮 (恒定新建语义, 读输入框)
btn.addEventListener('click', function () {
    createSessionFromInput();
});

// 回车直接新建
document.getElementById('cmd').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { createSessionFromInput(); }
});

// 侧边栏展开/收起: 覆盖层模式, 同步遮罩层状态并记忆偏好 (localStorage)
function setSidebarOpen(open) {
    sidebar.classList.toggle('open', open);
    sidebarOverlay.classList.toggle('open', open);
    localStorage.setItem(SIDEBAR_PREF_KEY, open ? '1' : '0');
}
if (localStorage.getItem(SIDEBAR_PREF_KEY) === '1') {
    setSidebarOpen(true);
}
sidebarToggle.addEventListener('click', function () {
    setSidebarOpen(!sidebar.classList.contains('open'));
});
// 点击遮罩层收起侧边栏
sidebarOverlay.addEventListener('click', function () {
    setSidebarOpen(false);
});

// 单击状态文字 → 切换控制键区显示/隐藏 (标记挂在 #control-keys 上, 避免被 setStatus 重写 className 清掉)
if (localStorage.getItem(KEYS_PREF_KEY) === '0') {
    controlKeys.classList.add('hidden');
}
statusEl.addEventListener('click', function () {
    controlKeys.classList.toggle('hidden');
    localStorage.setItem(KEYS_PREF_KEY, controlKeys.classList.contains('hidden') ? '0' : '1');
    // 控制键占高度, 显隐后重算前台终端尺寸
    if (activeSession) {
        try { activeSession.fit.fit(); } catch (err) { /* ignore */ }
        sendResize();
    }
});

// 窗口变化 → 前台 fit 重算 → onResize 自动发 resize 帧
window.addEventListener('resize', function () {
    if (activeSession) {
        try { activeSession.fit.fit(); } catch (err) { /* ignore */ }
        sendResize();
    }
});

// 页面加载 → 恢复服务端仍存活的会话 (刷新不丢终端)
restoreSessions();

// 带 ?cwd= 进入 (文件管理器「在终端中打开」) 且无存活会话时, 自动在指定目录开一个会话
if (URL_CWD && sessions.length === 0) {
    createSession('');
}
