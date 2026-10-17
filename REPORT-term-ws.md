# 远程终端 WS 修复报告（Invalid frame header + 刷新回放）

> 分支 `feat/term-multi-reconnect`，2026-10-14

## 一、WebSocket "Invalid frame header" 修复

### 症状

刷新/重连时浏览器控制台报 `WebSocket connection to 'ws://.../terminal/api/ws?...' failed: Invalid frame header`，伴随 1006 异常断连；新建终端正常，仅刷新恢复/抢占交接时出现。

### 根因链路

1. flask_sock 0.7.0 在 werkzeug 模式下，若 WSGI handler 正常返回（未抛异常），会走 `WebSocketResponse.__call__` 返回**普通 200 HTTP 响应**路径。
2. `wsTerminal` 在"同页抢占"场景（旧连接被新连接接管后失权退出主循环）属于**正常 return**——werkzeug 的 `execute()` 在 handler 返回后检测到 `headers_sent` 为假，向**已升级的 socket 补写 `HTTP/1.1 200 OK` 响应头**。
3. 浏览器此刻处于 CLOSING/未完成 close 握手状态仍在读帧，`H`(0x48) 等 ASCII 字节被当作 WebSocket 帧解析 → 帧头非法 → `Invalid frame header`（或 1006）。
4. 握手已完成才 return 的场景（如进程退出 exit 帧），浏览器已停止读帧，补写字节被安全忽略——这解释了"只有刷新恢复/抢占才报错"。

第一轮修复（`threaded=True`）方向错误：并发不足导致的是另一种非 101 响应问题，与真因并存但不是本症状主因。

### 修复（两处，均已上线验证）

| 位置 | 改动 | 作用 |
|------|------|------|
| `term_bp.py` `_sealSocketAfterClose` | 发送 close 帧后立即 `sock.shutdown(SHUT_WR)` 封锁写方向 | 浏览器收到 CLOSE+FIN 干净关闭；werkzeug teardown 的补写必然触发 `BrokenPipeError`，被其 `connection_dropped` 分支静默吞掉，补写字节**永远出不了网** |
| `term.js` `connectWs` 守卫 | 同一会话 `readyState <= 2` 时禁止重复建连 | 消除触发源：侧边栏重复点击已激活会话、快速连点"新建"会开出第二条 WS 挤掉旧连接，旧连接进入"存活时提前 return"病理路径 |

### 验证

- 受控复现（修复前）：连续刷新场景捕获病理模式 `hello ✓ →(45ms) 失权退出 → return 时 socket 存活 →(11ms) 前端 onclose code=1006 wasClean=false`，连续两次；干净场景（1001 正常关闭）从不报错——确证根因。
- 修复后：简单刷新 / 输出爆发期刷新 / 连续双刷新 / 同页连点 active 会话 / 快速交替切换，全部零报错；切换关闭为 `code=1005 wasClean=true`。
- 用户真实环境（端口 80）实测通过。

## 二、刷新恢复画面空白 + 鼠标点击/滚动失效修复

### 症状

整页刷新后终端列表与连接恢复，但画面空白（顶部历史缺失）；TUI 场景下点击、滚轮无响应。

### 根因

两个症状同源：刷新后的新 xterm 实例丢失了**全部转义序列状态**——历史输出（滚动区）、备用屏、鼠标跟踪模式（`?1000h` 等）、光标位置。

- 画面空白：服务端 `outQueue` 仅缓存**断开后**的输出，终端空闲期队列为空，断开前的历史已随旧连接发走。
- 鼠标失效：TUI 的鼠标事件依赖 mode 标志，新实例无此状态，退回本地模式但备用屏为空。

### 方案：服务端滚动回放缓冲（tmux attach 同款思路）

后端 `term_bp.py`：

- `TermSession` 增加 `replayBuf`（512KB 滚动缓冲，`REPLAY_MAX`）+ `replaySize`；`enqueueOut` 对 data 项先入回放缓冲再入队。
- `wsTerminal` 重连路径（`replay=1` 参数）按**不重不丢顺序**执行：
  1. `enqueueOut` 先 append `replayBuf` 再 put `outQueue` → 积压 ⊆ 快照；
  2. 快照 `replayBuf` → 清空 `outQueue`（丢弃与快照重复的积压）→ 发 hello → 逐块回放 → 主循环接实时流。
- 线程安全：`replayBuf` 仅 `_reader` 线程写，GIL 下 `append`/`pop(0)`/`list()` 均为 C 级原子操作，无需加锁。

前端 `term.js`：

- 会话对象增加一次性标志 `needReplay`（默认 false）；`restoreSessions` 恢复的 fresh 空终端置 true；`connectWs` 据此附加 `&replay=1`；hello 帧到达即消费（同页后续重连不回放，避免画面重复）。

### 验证

- **服务端确定性验证**（Python WS 客户端直连）：新会话写入 `echo testREPLAY001` → 断开 → 带 `replay=1` 重连 → `resumed=True`，回放完整历史；实时流无缝接续；回显命令行各出现恰好 1 次（无重复回放）——PASS。
- **浏览器端到端**（18080 测试实例 + 浏览器代理）：
  - 刷新后 40KB 历史输出（`dir /s`）经回放完整重建（buffer 长度 40333，含目录列表）；
  - 快速命令闭环：刷新 → 切换到目标会话 → `markOK123` 回显行+输出行完整出现（计数=2，无重复）；
  - 会话切换回归：切走再切回，画面保留、计数不变；
  - 滚轮：`.xterm-viewport.scrollTop` 0→112（scrollback 可滚）；
  - 聚焦：`term.focus()` 后 `document.activeElement` 为 `xterm-helper-textarea`（聚焦机制正常）；
  - 全程控制台零报错，无 `Invalid frame header`/1006。

### 已知边界

- `REPLAY_MAX=512KB` 只保留最近历史，超长滚动区最旧部分不回放（当前屏必在缓冲尾部）；
- 全屏 TUI 回放后由 resize 触发重绘，最终画面以重绘为准；
- 真实用户鼠标点击若仍有异常，优先排查点击坐标层（`elementFromPoint`），聚焦机制本身已验证正常。

## 三、提交记录

1. `8213fdf` feat(term): 多终端会话+断线重连+刷新恢复; 修复 WS Invalid frame header
2. 本次提交：feat(term): 刷新恢复画面回放缓冲 + 报告（replayBuf/REPLAY_MAX/needReplay + REPORT-term-ws.md）
