// 远程终端前端: multi=多会话 + 侧边栏 + 断线重连 + 心跳保活; single=Code 页内嵌单会话
// 每会话一个 xterm 实例; multi 模式仅前台会话持有 WebSocket, 后台会话切换时断开 WS (服务端保活, 进程不杀)。

// 常量
const PING_INTERVAL = 15000;    // 心跳间隔(ms), 保 NAT/中间设备链路
const RECONNECT_BASE = 1000;    // 重连退避基数(ms)
const RECONNECT_MAX = 30000;    // 重连退避封顶(ms)
const KEYS_PREF_KEY = 'showControlKeys';
const SIDEBAR_PREF_KEY = 'sidebarOpen';

// 嵌入配置: 普通 /terminal 页面不传, 保持 multi 全功能
const RC_CONFIG = Object.assign({
    embedded: false,
    mode: 'multi',
    terminalId: 'terminal',
    statusId: 'status',
    cwd: ''
}, window.RC_TERM_CONFIG || {});
const EMBEDDED = !!RC_CONFIG.embedded;
const TERM_MODE = RC_CONFIG.mode === 'single' ? 'single' : 'multi';

// 文件管理器「在终端中打开」: URL ?cwd= 作为新会话初始目录
const URL_CWD = new URLSearchParams(location.search).get('cwd') || '';
if (URL_CWD && !RC_CONFIG.cwd) { RC_CONFIG.cwd = URL_CWD; }

// 会话状态
let sessions = [];              // 全部会话
let activeSession = null;       // 当前前台会话 (仅此会话持有 ws)
let uidCounter = 0;

// DOM 引用 (Code 页只提供 terminal/status, 其余为 null)
const statusEl = document.getElementById(RC_CONFIG.statusId || 'status');
const btn = document.getElementById('connect');
const controlKeys = document.getElementById('control-keys');
const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebar-toggle');
const sidebarOverlay = document.getElementById('sidebar-overlay');
const displacedMask = document.getElementById('displaced-mask');
const reclaimBtn = document.getElementById('reclaim-btn');

function setStatus(text, cls) {
    if (statusEl) {
        statusEl.textContent = text;
        statusEl.className = cls || '';
    }
    if (EMBEDDED && window.CodeUI && window.CodeUI.status) {
        window.CodeUI.status(text, cls === 'err' ? 'error' : (cls === 'ok' ? 'ok' : ''));
    }
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
        case 'apoptotic': return '被接管';
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
    const termHost = document.getElementById(RC_CONFIG.terminalId || 'terminal');
    if (!termHost) { return null; }
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
        cwd: RC_CONFIG.cwd || '',
        term: term,
        fit: fit,
        el: container,
        ws: null,
        state: 'connecting',
        retryCount: 0,
        retryTimer: null,
        pingTimer: null,
        manualClose: false,
        needReplay: false,    // 一次性: fresh 空终端首次连接时向服务端请求画面回放, hello 后消费
        displacedDismissed: false,   // 凋亡态: 用户是否已关闭全屏卡片 (关闭后走工具条兜底入口)
        suppressData: false,        // 回放期间抑制 xterm 自动应答 (DA/DSR) 外发
        suppressTimer: null,        // 抑制兜底超时 (服务端未回 replayDone 时自动解除)
        replayPhase: false,         // 当前处于回放数据解析阶段 (hello 后到 replayDone 前)
        replayParsed: false,        // 已收到 replayDone
        pendingWrites: 0            // 回放数据中尚未解析完的 write 数
    };

    // 键盘输入只发给"本会话且本会话为前台"时的 ws
    term.onData(function (d) {
        if (session.suppressData) { return; }   // 回放中: 丢弃 DA/DSR 自动应答
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
    // single: 始终只保留一个会话, 重复调用等价于重建
    if (TERM_MODE === 'single' && sessions.length) {
        closeSession(sessions[0]);
    }
    const session = buildSessionUI(cmd);
    if (!session) { return null; }
    sessions.push(session);
    switchSession(session);
    return session;
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
    updateDisplacedUI();
    if (session.state === 'ended') {
        // 已退出/错误会话: 不重连, 仅展示定格画面
        setStatus('已退出: ' + session.cmd, 'err');
        return;
    }
    if (session.state === 'apoptotic') {
        // 凋亡会话: 切前台不自动抢占, 等用户点「重新接管」, 避免与对方互踢
        setStatus('终端已被其他设备接管', 'err');
        updateDisplacedUI();
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
    updateDisplacedUI();
}

// 页面加载时拉取服务端存活会话列表, 重建终端列表并重连恢复
// (断线重连由 onclose 处理; 此处专门处理整页刷新: 前端 sessions 清空, 需向服务端重新询问)
function restoreSessions() {
    if (TERM_MODE === 'single' || EMBEDDED) { return; }
    return fetch('/terminal/api/sessions')
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
    if (session.suppressTimer) { clearTimeout(session.suppressTimer); session.suppressTimer = null; }
}

// ---------------------------------------------------------------------------
// 凋亡 / 坏死
//   凋亡 (displaced): 服务端发 displaced 帧 —— 会话被其他客户端抢占, 进程仍保活。
//                     停止自动重连, 弹出全屏卡片等用户点「重新接管」。
//   坏死 (网络):     没有 displaced 帧的 onclose, 按指数退避自动重连 (无需点击)。
// ---------------------------------------------------------------------------

// 按当前前台会话状态同步遮罩与工具条兜底入口
function updateDisplacedUI() {
    const s = activeSession;
    const apoptotic = !!(s && s.state === 'apoptotic');
    if (displacedMask) {
        displacedMask.classList.toggle('hidden', !(apoptotic && !s.displacedDismissed));
    }
    if (reclaimBtn) {
        reclaimBtn.classList.toggle('hidden', !(apoptotic && s.displacedDismissed));
    }
}

// 回放数据全部解析完才解除输入抑制。
// xterm 的 write() 是异步解析: replayDone 到达时回放可能仍在队列里,
// 若此时就放行 onData, 解析回放内容产生的设备应答会在之后发往 pty。
function releaseSuppressIfDone(session) {
    if (!session.suppressData) { return; }
    if (!session.replayParsed || session.pendingWrites > 0) { return; }
    session.suppressData = false;
    if (session.suppressTimer) {
        clearTimeout(session.suppressTimer);
        session.suppressTimer = null;
    }
}

// 用户点击「重新接管」: 丢弃旧连接 -> 重新 attach (保留本地画面)
function reclaimSession(session) {
    if (!session) { return; }
    clearTimers(session);
    if (session.ws) {
        // 先置空再关闭: 旧 socket 的 onclose 因 session.ws !== socket 被忽略
        const old = session.ws;
        session.ws = null;
        try { old.close(); } catch (err) { /* ignore */ }
    }
    session.manualClose = false;
    session.displacedDismissed = false;
    session.state = 'connecting';
    // 不回放: 本端 xterm 画面/模式序列一直都在, 清屏重放会让历史里的 ESC[c
    // 重新触发 xterm 的设备属性应答 (?1;2c), 该应答会作为输入发给 shell,
    // 把用户下一条命令拼成乱码。接管只重新 attach, 不改本地画面。
    setStatus('重新接管中: ' + session.cmd);
    updateDisplacedUI();
    connectWs(session);
}

function reclaimActiveSession() {
    reclaimSession(activeSession);
}

function connectWs(session) {
    // 防抢占: 同一会话已有存活/半关闭连接时禁止重复建连
    // (否则服务端对旧连接失权退出, 旧连接浏览器侧报 1006/Invalid frame header;
    //  典型触发: 侧边栏重复点击已激活会话、快速连点"新建")
    if (session.ws && session.ws.readyState <= 2) { return; }
    clearTimers(session);
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    let url = proto + '://' + location.host + '/terminal/api/ws?cmd=' + encodeURIComponent(session.cmd)
        + '&mode=' + encodeURIComponent(TERM_MODE);
    if (session.cwd) { url += '&cwd=' + encodeURIComponent(session.cwd); }
    if (TERM_MODE === 'multi' && session.sessionID) { url += '&session=' + encodeURIComponent(session.sessionID); }
    if (TERM_MODE === 'multi' && session.needReplay) { url += '&replay=1'; }
    // 回放期间抑制 xterm 的自动应答: 回放内容里的 DA 查询会生成 (?1;2c),
    // 放行会把应答当输入写进 pty, 污染 shell 输入缓冲。
    session.suppressData = (TERM_MODE === 'multi' && session.needReplay);
    session.replayPhase = false;
    session.replayParsed = false;
    session.pendingWrites = 0;
    if (session.suppressData) {
        // 兜底: 老服务端没有 replayDone 帧时, 5s 后无条件恢复输入
        session.suppressTimer = setTimeout(function () {
            session.suppressData = false;
            session.suppressTimer = null;
        }, 5000);
    }
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
            if (session.replayPhase) {
                // 回放阶段: 统计未解析完的数据块, 全部完成后才恢复输入
                session.pendingWrites++;
                session.term.write(e.data, function () {
                    session.pendingWrites--;
                    releaseSuppressIfDone(session);
                });
            } else {
                session.term.write(e.data);
            }
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
        if (session.state === 'apoptotic') {
            // 凋亡: 已收到 displaced 帧, 等用户点击「重新接管」, 不自动重连
            renderSidebar();
            updateDisplacedUI();
            return;
        }
        if (session.manualClose) {
            // 主动断开 (切换/关闭): multi 服务端保活, 不重连
            renderSidebar();
            return;
        }
        if (TERM_MODE === 'single') {
            // single: 连接结束即会话结束, 由 Code 页在需要时重建
            session.state = 'ended';
            setStatus('终端已断开 (code ' + e.code + ')', 'err');
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
        if (session.suppressData) {
            // 本次连接带 replay=1: 进入回放解析阶段, 期间丢弃自动应答
            session.replayPhase = true;
            session.replayParsed = false;
            session.pendingWrites = 0;
        }
        if (obj.resumed === false) {
            session.term.reset();   // 新进程: 清空; resumed=true 时保留画面 (现场恢复)
            // 新进程不会回放 (服务端 wantReplay 要求 resumed), 立即解除输入抑制,
            // 否则要等 5s 兜底超时才能输入
            session.replayParsed = true;
            releaseSuppressIfDone(session);
        }
        session.state = 'connected';
        setStatus('已连接: ' + (obj.cmd || session.cmd), 'ok');
        try { session.fit.fit(); } catch (err) { /* ignore */ }
        sendResizeFor(session);
        renderSidebar();
        updateDisplacedUI();          // 已恢复连接: 收起凋亡遮罩/兜底按钮
        return;
    }
    if (obj.type === 'displaced') {
        // 凋亡: 被其他客户端抢占。不进入重连态, 等用户手动接管
        clearTimers(session);
        session.state = 'apoptotic';
        session.displacedDismissed = false;
        // 不置 needReplay: 本地画面保持原样, 接管时只重新 attach
        setStatus('终端已被其他设备接管', 'err');
        renderSidebar();
        updateDisplacedUI();
        return;
    }
    if (obj.type === 'replayDone') {
        // 回放帧已发完; 等待 xterm 解析队列排空后再恢复输入 (见 releaseSuppressIfDone)
        session.replayPhase = false;
        session.replayParsed = true;
        releaseSuppressIfDone(session);
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
    // single 不自动重连; 仅前台 multi 会话重连
    if (TERM_MODE === 'single' || session !== activeSession) { return; }
    session.retryCount += 1;
    session.state = 'reconnecting';
    const delay = Math.min(RECONNECT_BASE * Math.pow(2, session.retryCount - 1), RECONNECT_MAX);
    // 坏死: 显示指数退避的实际等待秒数, 让用户知道下次重试时间
    setStatus('重连中 (第 ' + session.retryCount + ' 次, ' + Math.round(delay / 1000) + 's 后重试)', 'err');
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

function fitActive() {
    if (!activeSession || !activeSession.el || activeSession.el.hidden) { return; }
    if (!activeSession.el.clientWidth || !activeSession.el.clientHeight) { return; }
    try { activeSession.fit.fit(); } catch (err) { /* ignore */ }
}

// "新建" 按钮 (恒定新建语义, 读输入框)
if (btn) {
    btn.addEventListener('click', function () {
        createSessionFromInput();
    });
}

// 回车直接新建
const cmdInput = document.getElementById('cmd');
if (cmdInput) {
    cmdInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { createSessionFromInput(); }
    });
}

// 侧边栏展开/收起: 覆盖层模式, 同步遮罩层状态并记忆偏好 (localStorage)
function setSidebarOpen(open) {
    if (!sidebar || !sidebarOverlay) { return; }
    sidebar.classList.toggle('open', open);
    sidebarOverlay.classList.toggle('open', open);
    localStorage.setItem(SIDEBAR_PREF_KEY, open ? '1' : '0');
}
if (sidebar && localStorage.getItem(SIDEBAR_PREF_KEY) === '1') {
    setSidebarOpen(true);
}
if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', function () {
        setSidebarOpen(!sidebar.classList.contains('open'));
    });
}
// 点击遮罩层收起侧边栏
if (sidebarOverlay) {
    sidebarOverlay.addEventListener('click', function () {
        setSidebarOpen(false);
    });
}

// 凋亡态交互: 全屏卡片主/次按钮 + 工具条兜底按钮
const displacedReclaim = document.getElementById('displaced-reclaim');
if (displacedReclaim) {
    displacedReclaim.addEventListener('click', function () { reclaimActiveSession(); });
}
const displacedDismiss = document.getElementById('displaced-dismiss');
if (displacedDismiss) {
    displacedDismiss.addEventListener('click', function () {
        if (activeSession) { activeSession.displacedDismissed = true; }
        updateDisplacedUI();
    });
}
if (reclaimBtn) {
    reclaimBtn.addEventListener('click', function () { reclaimActiveSession(); });
}

// 单击状态文字 → 切换控制键区显示/隐藏 (标记挂在 #control-keys 上, 避免被 setStatus 重写 className 清掉)
if (controlKeys && localStorage.getItem(KEYS_PREF_KEY) === '0') {
    controlKeys.classList.add('hidden');
}
if (statusEl && controlKeys) {
    statusEl.addEventListener('click', function () {
        controlKeys.classList.toggle('hidden');
        localStorage.setItem(KEYS_PREF_KEY, controlKeys.classList.contains('hidden') ? '0' : '1');
        // 控制键占高度, 显隐后重算前台终端尺寸
        fitActive();
        sendResize();
    });
}

// 窗口变化 → 前台 fit 重算 → onResize 自动发 resize 帧
window.addEventListener('resize', function () {
    fitActive();
    sendResize();
});

// 面板显隐/缩放 → 重新 fit (Code 页折叠/展开终端时尤其需要)
if (typeof ResizeObserver !== 'undefined') {
    const termHost = document.getElementById(RC_CONFIG.terminalId || 'terminal');
    if (termHost) {
        const resizeObserver = new ResizeObserver(function () {
            fitActive();
            sendResize();
        });
        resizeObserver.observe(termHost);
    }
}

// Code 页可调用的稳定接口
window.rcTerm = {
    createSession: function (cmd) {
        return createSession(cmd || 'powershell.exe');
    },
    closeActive: function () {
        if (activeSession) { closeSession(activeSession); }
    },
    sendCommand: function (command) {
        if (!activeSession || !activeSession.ws || activeSession.ws.readyState !== 1) {
            return false;
        }
        activeSession.ws.send(String(command) + '\r');
        return true;
    },
    fit: function () {
        fitActive();
        sendResize();
    },
    focus: function () {
        if (activeSession && activeSession.term) {
            try { activeSession.term.focus(); } catch (err) { /* ignore */ }
        }
    },
    isReady: function () {
        return !!(activeSession && activeSession.state === 'connected'
            && activeSession.ws && activeSession.ws.readyState === 1);
    },
    waitReady: function (timeout) {
        const deadline = Date.now() + (timeout || 15000);
        return new Promise(function (resolve) {
            (function check() {
                if (window.rcTerm.isReady()) { resolve(true); return; }
                if (Date.now() >= deadline) { resolve(false); return; }
                setTimeout(check, 100);
            })();
        });
    },
    getSessionId: function () {
        return activeSession ? activeSession.sessionID : null;
    },
    setCwd: function (cwd) {
        RC_CONFIG.cwd = cwd || '';
    }
};

// 页面加载 → 恢复服务端仍存活的会话 (刷新不丢终端; single/embedded 不恢复)
restoreSessions();

// 带 ?cwd= 进入 (文件管理器「在终端中打开」) 且无会话可恢复时, 自动在指定目录开一个会话
Promise.resolve(restoreSessions()).then(function () {
    if (URL_CWD && !EMBEDDED && sessions.length === 0) {
        createSession('');
    }
});
