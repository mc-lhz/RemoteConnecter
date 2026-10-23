# 远程终端：多终端（隐藏式侧边栏）+ 断线重连（会话保活）

## 摘要

将 `functions/term/` 从"单终端、WS 与进程强绑定"改造为：

1. **后端会话化**：新增 `TermSession` 会话对象 + 全局会话注册表。WS 断开 ≠ 进程销毁；进程保活（默认 5 分钟宽限期），重连带 `session` 参数恢复原会话（登录态、后台任务、输出全部保留）。
2. **前端侧边栏多终端**：默认隐藏的左侧会话栏（`+` 新建 / 点击切换 / `×` 关闭），每会话独立 xterm 实例，切换时断开旧 WS（进程保活）、连新 WS 恢复现场。
3. **前端自动重连**：活动 WS 异常断开后按指数退避（1s→30s 封顶）无限重连，带 `session` 参数恢复；前端 15s 心跳 ping 保 NAT 链路。

无新增依赖；`build.cmd` / `hosts/` 零改动（`functions/term` 已在扫描范围内）。

## 现状分析（已核实）

- `functions/term/term_bp.py:123` `wsTerminal(ws)`：进程/队列/事件全部是 handler 闭包局部变量（`procRef`/`spawned`/`outQueue`/`stop`），WS 断开时 `finally` 直接 `terminate()` 杀进程 → **断线即丢现场，无法恢复**。
- 已有模型（必须保留）：reader 线程同线程 spawn+read（pywinpty 线程亲和性）→ `outQueue` → WS 主线程统一 `ws.send`（wsproto 不支持并发 send）；`b'0011Ignore'` 哨兵空串 ≠ EOF；Windows write 收 str（LF→CR）。
- 帧协议已有 ping/pong 定义（`term_bp.py:281`）但前端从未发 ping，形同虚设；无任何会话 ID / 注册表 / 宽限回收。
- `functions/term/static/term.js`：全局单例 `term`/`ws`，单终端；`ws.onclose` 只改状态文字，不重连。
- `functions/update/static/update-api.js` 有现成的前端重连惯例（退避 + 状态文案）可参考。
- 项目强约束（MEMORY.md）：标识符小驼峰、类名 PascalCase、常量全大写；不用 asyncio，纯 threading；错误处理宽 try/except + `Logcat` 记日志；HTML 内联 onclick 惯例（见 term.html 预设按钮）。

## 方案设计

### 1. 帧协议扩展（`wsTerminal` docstring 同步更新）

前端→后端（不变 + 1 新增）：
- 文本帧：原始按键（不变）
- `{"type":"resize","cols":..,"rows":..}`（不变）
- `{"type":"ping"}`（不变，前端开始真正使用）
- `{"type":"close"}` **新增**：显式终止会话（杀进程 + 移出注册表）

后端→前端（不变 + 1 新增）：
- 文本帧：VT 输出（不变）
- `{"type":"exit","code":..}` / `{"type":"error","msg":..}`（不变）
- `{"type":"hello","session":"<id>","resumed":true|false,"cmd":"..."}` **新增**：attach 成功后的第一帧。`resumed=true` 表示恢复了保活进程（前端不 `term.reset()`，画面连续）；`false` 表示新进程（前端 reset）。

WebSocket 路由：`/terminal/api/ws?cmd=..&cwd=..&session=<id>`（`session` 可选）
- 无 `session` / 查无此会话 / 会话已退出 → 新开会话（spawn 新进程），hello `resumed:false`
- `session` 命中存活会话 → attach 复用进程，hello `resumed:true`

### 2. 后端：会话对象 + 注册表 + 回收（term_bp.py 重构）

新增（全部模块级，小驼峰；类名 PascalCase；常量全大写）：

```python
import time, uuid
DETACH_TIMEOUT = 300   # 会话无人附着宽限期(秒)，超时杀进程
REAPER_INTERVAL = 10   # 回收线程扫描周期(秒)
MAX_BACKLOG = 20000    # 会话无人附着时输出队列上限(条)，超出丢最旧

sessionMap = {}        # {sessionID: TermSession}
sessionMapLock = threading.Lock()
reaperStarted = False  # 回收线程惰性启动标记
reaperLock = threading.Lock()

class TermSession:
    """终端会话: 与 WS 解耦, 进程在 WS 断开后继续存活"""
    def __init__(self, sessionID, cmd, cwd):
        self.sessionID = sessionID
        self.cmd = cmd
        self.cwd = cwd
        self.proc = None          # reader 线程内创建
        self.alive = False        # spawn 成功置 True; 退出/失败置 False
        self.attached = None      # 当前附着 ws (单附着, 抢占式接管)
        self.sessionLock = threading.Lock()
        self.outQueue = queue.Queue()
        self.stop = threading.Event()
        self.spawned = threading.Event()
        self.lastDetachAt = 0.0   # 最近一次进入无人附着状态的时间戳
```

关键函数（均为模块级函数，沿用现有 reader 模式）：

- `newSession(cmd, cwd)`：建 TermSession → 入 `sessionMap` → 启动 reader 线程 → 惰性启动回收线程 → 返回 session。
- `reader(session)`（由现 `wsTerminal` 内 reader 闭包抽出，逻辑不变）：同线程内 `spawnShell`；异常 → 入队 `('error', ...)`；EOF → 入队 `('exit', code)`。无论何种终结：**置 `session.alive=False` 并从 `sessionMap` 移除**（此后重连自动降级为新开会话）。队列封顶：`put` 后 `while outQueue.qsize() > MAX_BACKLOG: get_nowait()` 丢最旧。
- `sessionReaper()`（daemon 线程，10s 一轮）：遍历 `sessionMap`，`alive=True` 且 `attached is None` 且 `time.time() - lastDetachAt > DETACH_TIMEOUT` → `terminateSession(session)`。
- `terminateSession(session)`：`stop.set()` + `proc.terminate()` + `proc.close()` + 从 `sessionMap` 移除（幂等，`Log.i` 记录）。
- `wsTerminal(ws)` 重构流程：
  1. 取参 `cmd/cwd/sessionID`；`sessionID` 命中存活会话则复用，否则 `newSession`。
  2. `with session.sessionLock: session.attached = ws`（**抢占式接管**：旧附着者存在时不跨线程 close 它的 ws，旧循环靠下面的"失权检测"自行退出，避免 wsproto 跨线程操作）。
  3. `spawned.wait(15)` 逻辑不变（仅新会话会等待；复用会话 spawned 已 set）。
  4. 发 hello 帧（`resumed` = 本次 attach 前 `session.alive` 已为 True）。
  5. 主循环（在现主循环基础上加**失权检测**）：每轮先 `with session.sessionLock: mine = (session.attached is ws)`，`mine` 为 False（被抢占或会话被终结）→ break；否则排空 `outQueue` 统一 send、`ws.receive(timeout=0.05)`、控制帧处理。
  6. `finally`：`with session.sessionLock: if session.attached is ws: session.attached = None; session.lastDetachAt = time.time()`（**不再 terminate**——保活核心改动）。
- `_handleControl` 增加 `close` 分支：发 `{"type":"pong"}` 不变；`close` → `terminateSession(session)`（需要把 session 传入，签名 `_handleControl(ws, session, payload)`，内部用 `session.proc`）。
- 现有 `spawnShell`/`_spawnWindows`/`_PipeProcess`/`_decodeFrame` **零改动**。
- 日志：spawn / attach(resumed?) / detach / terminate / reap 各加一条 `Log.i('term', ...)`（`import Logcat; Log = Logcat.Logcat()`，对齐项目惯例）。

### 3. 前端：侧边栏多终端 + 自动重连（term.js 重写 + term.html/term.css 增补）

**布局**（term.html）：`body` 改为 flex row：`#sidebar`（默认 `display:none`，展开约 200px）+ `#main`（原 `#bar` + `#terminal` 宿主 + `#control-keys` 原样保留，竖排不变）。
- `#sidebar` 内容：头部（"终端" 标题 + `#sidebar-add` 的 `+` 按钮）+ `#session-list`（`<ul>`，由 JS 渲染）。
- `#bar` 改动：最左侧加 `#sidebar-toggle`（☰ 图标按钮，切换侧边栏，localStorage 键 `sidebarOpen` 记忆，对齐 `showControlKeys` 惯例）；原 `#connect` 按钮改为恒定"新建"语义（读 `#cmd` 输入框/预设按钮设置的 `globalCmd`，调 `createSession`）；预设 cmd/powershell 按钮 onclick 改为 `globalCmd = '...'; createSession(globalCmd)`；`#status` 保留（单击切换控制键的既有行为不动）。
- 会话 DOM 结构：每个会话一个 `<div class="session-terminal" hidden>`（内部 xterm 容器）常驻 `#terminal` 宿主区，切前台的显示、其余 `hidden`（xterm DOM renderer 对 display:none 无副作用；切回时 `fit.fit()` 重算尺寸）。**不移动/不重新 open 已初始化的 xterm 实例**。

**term.js 重写**（保持原生 JS、let/const + 函数声明、小驼峰；删除现有全局 `term`/`ws` 单例语义，改为每会话对象）：

```js
// 每会话对象字段
{
  uid,            // 客户端本地唯一 id
  sessionID,      // 服务端会话 id (首次连接前为 null, hello 帧后填入)
  cmd,            // 启动命令 (用于侧边栏显示与重连 URL)
  term,           // xterm Terminal 实例
  fit,            // FitAddon
  el,             // 该会话的 xterm 容器 div
  ws,             // 当前 WebSocket (未连接为 null)
  state,          // 'connecting' | 'connected' | 'reconnecting' | 'ended'
  retryCount,     // 当前重连退避计数
  retryTimer,     // 重连 setTimeout 句柄
  pingTimer,      // 心跳 setInterval 句柄
  manualClose,    // 主动断开标记 (切换/关闭时为 true, 抑制自动重连)
}
let sessions = [];          // 全部会话
let activeSession = null;   // 当前前台会话 (仅此会话持有 ws)
```

核心函数：

- `createSession(cmd)`：建会话对象（xterm 同现有配置）→ 入 `sessions` → `switchSession(session)`。
- `switchSession(session)`：
  1. 若 `activeSession` 且 `activeSession !== session`：清其 ping/retry 定时器、置 `manualClose=true`、`ws.close()`（**服务端保活，进程不杀**）、`activeSession.ws = null`。
  2. `activeSession = session`；显示其 `el`、隐藏其余；`fit.fit()`；`connectWs(session)`。
  3. `renderSidebar()`。
- `connectWs(session)`：清旧定时器；url = `/terminal/api/ws?cmd=..` +（`session.sessionID` 存在时 `&session=..`）；`state='connecting'`（已有 sessionID 且断线恢复中则 `'reconnecting'` 并显示第 n 次）；`new WebSocket`：
  - `onopen`：清 `retryCount`；**等 hello 帧再决定 reset**（见 onmessage）；启动 pingTimer（15s 发 `{"type":"ping"}`）。
  - `onmessage`：JSON.parse 成功且 `obj.type` 存在 → 控制帧：
    - `hello`：填 `session.sessionID = obj.session`；`obj.resumed === false` 时 `term.reset()`；`state='connected'`；`fit.fit()` + `sendResize()`；`renderSidebar()`。
    - `exit`：`state='ended'`；xterm 写入退出提示（沿用现有文案）；**不重连**；清理 ws 与定时器。
    - `error`：xterm 写错误提示；`state='ended'`；不重连。
    - `pong`：忽略。
    - 解析失败 → 原始 VT 输出 `term.write(e.data)`。
  - `onclose`：`session.ws = null`；若 `manualClose` 或 `state==='ended'` → 仅更新 UI；否则 `scheduleReconnect(session)`。
- `scheduleReconnect(session)`：仅当 `session === activeSession` 时执行（后台会话无 ws 无需重连，切回时由 `switchSession→connectWs` 自然恢复）；指数退避 `Math.min(1000 * 2**retryCount, 30000)`，`retryCount++` 后 `setTimeout(connectWs)`；`state='reconnecting'`；`renderSidebar()`（显示"重连中 n"）。**不限重试次数**——服务端重启后旧 sessionID 失效，后端自动新开会话（`resumed:false` → reset），前端无需特判。
- `closeSession(session)`（侧边栏 `×`）：若该会话 ws 开着，先发 `{"type":"close"}` 再 `ws.close()`（`manualClose=true` 抑制重连）；`term.dispose()`；从 `sessions` 移除；若为前台 → `activeSession` 切到剩余最后一个（无则置 null，状态栏"未连接"）；`renderSidebar()`。
- `sendControlKey(seq)` / `sendResize()`：改作用于 `activeSession`（`activeSession && ws && ws.readyState===1`）。
- `renderSidebar()`：全量重渲 `#session-list`：每项 `cmd` + 状态点/状态文字（连接中/已连接/重连中 n/已退出）+ `×` 按钮；前台项加 active 高亮；点击项 → `switchSession`，点击 `×`（`stopPropagation`）→ `closeSession`。
- `#sidebar-toggle`：切换 `#sidebar` 显隐 + `localStorage('sidebarOpen')`；`#sidebar-add` 的 `+` → 用当前输入框值 `createSession`。
- 既有 `term.onData` / `window resize` / 控制键显隐逻辑保留，作用域改到 `activeSession`。

**term.css 增补**：`body{display:flex;flex-direction:row}`，`#main{flex:1;display:flex;flex-direction:column;min-width:0}`，`#sidebar`（200px 宽、`#161b22` 底、`display:none`，`.open{display:flex}`）+ 会话列表项样式（hover 出 `×`、active 高亮 `#58a6ff` 系）；`#sidebar-toggle` 小方按钮风格对齐 `.preset-command`；窄屏（≤640px）侧边栏改绝对定位覆盖层（`position:fixed;left:0;top:0;bottom:0;z-index`），避免挤压终端。

## 具体改动清单

| 文件 | 改动 |
|---|---|
| `functions/term/term_bp.py` | 重构：新增 `TermSession`/`sessionMap`/`newSession`/`reader`/`sessionReaper`/`terminateSession` 与 3 个常量；`wsTerminal` 改为 attach/detach 流程（finally 不再杀进程）；`_handleControl` 加 `close` 分支并改签名传 session；协议 docstring 补 hello/close；加 Log 日志。`spawnShell`/`_spawnWindows`/`_PipeProcess`/`_decodeFrame`/路由不动 |
| `functions/term/static/term.js` | 按上述设计重写（单例 → 会话数组 + 侧边栏 + 重连 + 心跳） |
| `functions/term/templates/term.html` | 加 `#sidebar`（头部 + `#session-list`）与 `#sidebar-toggle`；`#connect` 改"新建"语义与文案；预设按钮 onclick 改 `createSession`；xterm 容器改由 JS 动态建（`#terminal` 作为宿主保留） |
| `functions/term/static/term.css` | body 改 row 布局、`#main` 包裹、侧边栏/列表项/开关按钮样式、窄屏覆盖层 |
| `MEMORY.md` | 实现完成后更新"当前状态"与"历史改动"（项目维护惯例） |

不改动：`hosts/*`、`RemoteConnecter.py`、`build.cmd`（`functions/term` 的 `*_bp` 与 `templates/static` 均已被自动扫描；无新文件类型/新目录）。

## 假设与决策

1. **单附着、抢占式接管**：一个会话同一时刻只有一个 WS 附着；后到者直接接管 `attached`，旧循环每轮"失权检测"自行退出（不跨线程 close 对方 ws，规避 wsproto 线程安全问题）。单操作者场景为主；双浏览器同会话属边缘情况，旧端表现为静默断开。
2. **重连只针对前台会话**：后台会话没有 WS（切换即 detach），无需重连逻辑；切回时 `connectWs` 天然走恢复路径。
3. **进程退出即销毁会话**：`exit`/启动失败后立即移出注册表（不保留"已死会话"墓碑），重连命中失效 id 时后端自动新开会话（`resumed:false`）。
4. **页面刷新后侧边栏清空**：侧边栏是浏览器本地状态，不做服务端会话列表 API（孤儿会话由 5 分钟宽限期自然回收）——控制范围，避免为低频场景加接口。
5. **宽限期固定 5 分钟**（`DETACH_TIMEOUT`），不做配置项。
6. **心跳仅前端 15s ping**（保 NAT/中间设备链路）；后端不单设 ping 定时器——WS 断链时 `receive` 抛异常即可感知，够用。
7. 沿用现有 `cmd.exe` 默认命令与 `cwd` 默认值（`~`）。
8. `hello` 必须是客户端收到的第一帧（attach 成功即发，主循环之前），保证 reset 决策先于任何输出。

## 验证步骤

1. 开发态启动（`python RemoteConnecter.py`，端口 80），浏览器开 `/terminal`。
2. **新建/切换**：`+` 新建 cmd 终端，输入 `echo test-<随机>`；再新建 powershell 终端；切回 cmd → 屏幕画面连续保留（hello `resumed:true`、不 reset）。
3. **保活重连（核心）**：前台终端执行一个长任务（如 `ping 127.0.0.1 -n 300`）；DevTools → Network 切 Offline 数秒再恢复 → 观察"重连中"退避 → 自动重连成功、画面连续、任务输出不断（服务端进程未死）。
4. **会话终结**：终端内 `exit` → 收到 exit 帧 → 侧边栏显示"已退出"、不出现重连。
5. **显式关闭**：侧边栏 `×` → 进程被杀（`tasklist | findstr cmd` 对比，或观察 Log 日志 terminate 记录）；该会话消失。
6. **宽限回收**：临时把 `DETACH_TIMEOUT` 调小（如 20s）验证 reaper 日志 reap 记录后还原；或保持 300s 只确认 detach 日志存在。
7. **多浏览器/抢占（边缘，可选）**：两个浏览器用同一 `session` 参数连同一会话，后到者接管、先到者断开，无异常日志。
8. **回归**：控制键（含 Enter）、单击状态文字显隐控制键（localStorage）、窗口 resize 同步、预设按钮、自定义命令回车新建；非 Windows 回退路径（`_PipeProcess`）冒烟。
9. `GetDiagnostics` 确认无语法/静态错误；通读命名逐项核对小驼峰（Python 变量/函数/属性、JS 标识符；类名 `TermSession` PascalCase；常量全大写；HTML id/class 维持 kebab 惯例）。
