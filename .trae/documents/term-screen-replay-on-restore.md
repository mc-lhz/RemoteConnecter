# 终端刷新恢复：服务端画面回放缓冲

## 第 0 步：先 push 当前修复（用户要求，执行方案前完成）

提交并推送 Invalid frame header 修复：`git add` `functions/term/term_bp.py`、`functions/term/static/term.js`、`RemoteConnecter.py`、`MEMORY.md`，一次提交，push 到 `feat/term-multi-reconnect`。不夹带回放方案改动，不写报告。

## 摘要

修复"整页刷新后终端恢复连接但画面空白（顶上内容缺失）"及"终端不可点击、无法滚动"两个缺陷。方案：服务端为每个终端会话维护一个滚动输出缓冲区（约 512KB），前端恢复 fresh 会话时通过 `replay=1` 参数请求回放，服务端先回放历史输出再接入实时流。tmux attach 同款思路，不新增前端依赖。

**两个问题同根同源**：新 xterm 实例刷新后丢失全部转义序列状态（备用屏、鼠标跟踪模式 `?1000h`、光标位置、字符集）。画面空白是"没有内容"；点击/滚轮失效是 TUI 的鼠标事件依赖的 mode 标志丢失——xterm 退回本地模式但备用屏为空（截图证据：`/ses` 菜单是 resize 触发的服务端 TUI 重绘，说明键盘路径经服务端正常，唯 xterm 本地鼠标状态缺失）。回放字节流会把这些 mode 设置序列一并重建，一个修复覆盖两个症状。

## 现状分析

- 刷新 → 前端 `restoreSessions()` 拉取 `/terminal/api/sessions` 重建会话 UI → `connectWs` 带 `session=<id>` 重连 → 服务端 `wsTerminal` attach 复用进程（`resumed=True`）。
- **空白根因**：attach 后服务端只排空 `outQueue`——它仅含**断开之后**产生的输出；终端空闲期无输出，队列为空，断开前的历史输出已随旧连接发走，新终端无内容可渲染。之后前端发 resize 帧触发 TUI 局部重绘，只能恢复部分画面（用户截图：opencode 界面居中重绘、顶部历史缺失）。
- 现有架构关键事实（已通读代码确认）：
  - 输出唯一通道：`_reader` 线程 → `session.enqueueOut(('data', payload))` → ws 主循环排空 `outQueue` 发送；
  - `enqueueOut` 中 winpty 返回 `str`、非 Windows `_PipeProcess` 返回 `bytes`；
  - `outQueue` 有 `MAX_BACKLOG=20000` 条封顶丢最旧；
  - 前端 `hello` 帧处理：`resumed=false` 才 `term.reset()`，`resumed=true` 保留画面（为同页重连设计，刷新场景终端本是空的，无碍）；
  - 同页重连（网络闪断/切后台会话切回）依赖 `outQueue` 排空补差量，画面保留不重置——此正确行为必须保留。

## 方案设计

### 数据流与顺序（防重不防丢的关键）

```
_reader 线程:   enqueueOut: ① append → replayBuf (滚动截断)
                             ② put → outQueue
attach(replay=1):
  ③ replaySnapshot = list(replayBuf)   # 快照
  ④ 清空 outQueue                       # 积压 ⊆ 快照（①先于②），丢弃防重复
  ⑤ 发 hello(resumed=true)
  ⑥ 逐块发送 replaySnapshot             # 历史回放
  ⑦ 进入主循环                          # 排空 outQueue → 快照后新输出，顺序在回放之后
```

竞态正确性：快照③与清空④之间新到的块，因 ①先append后put，已在快照中且被④从队列丢弃——不重不丢；④之后新到的块只在队列，主循环⑦发送且时序在回放后。`replayBuf` 仅 `_reader` 线程写，`append`/`pop(0)` 为 C 级原子操作，CPython GIL 下与主线程 `list()` 快照并发安全，不加锁（注释说明）。

### 改动文件

#### 1. functions/term/term_bp.py（后端，4 处小改）

- **常量**（紧跟 `MAX_BACKLOG` 后）：
  ```python
  REPLAY_MAX = 512 * 1024   # 回放缓冲上限(字符/字节近似), 重建画面用, 超出丢最旧
  ```
- **TermSession.__init__** 增加两字段：
  ```python
  self.replayBuf = []    # 输出滚动缓冲 (str/bytes 块), 供重连回放重建画面
  self.replaySize = 0    # replayBuf 近似大小 (str 计字符数, bytes 计字节数)
  ```
- **enqueueOut**：`kind == 'data'` 时先入回放缓冲并截断，再入队（原有 outQueue 封顶逻辑不动）：
  ```python
  def enqueueOut(self, item):
      """输出入队 + 队列封顶 + 回放缓冲维护 (仅 _reader 线程调用, GIL 下无需加锁)。"""
      kind, payload = item
      if kind == 'data':
          self.replayBuf.append(payload)
          self.replaySize += len(payload)
          while self.replaySize > REPLAY_MAX and self.replayBuf:
              removed = self.replayBuf.pop(0)
              self.replaySize -= len(removed)
      self.outQueue.put(item)
      while self.outQueue.qsize() > MAX_BACKLOG:
          ...  # 原逻辑不变
  ```
- **wsTerminal**：在 `spawned.wait` 之后、hello 帧前后插入回放段（attach 已完成）：
  ```python
  # 画面回放: 前端 fresh 恢复时带 replay=1, 服务端先回放历史输出再接实时流
  wantReplay = resumed and request.args.get('replay') == '1'
  replaySnapshot = []
  if wantReplay:
      replaySnapshot = list(session.replayBuf)          # ③ 快照
      while True:                                        # ④ 丢弃与快照重复的积压
          try:
              session.outQueue.get_nowait()
          except queue.Empty:
              break
  # (现有 hello 帧发送)
  if replaySnapshot:
      for chunk in replaySnapshot:                       # ⑥ 回放
          try:
              ws.send(chunk if isinstance(chunk, str)
                      else chunk.decode('utf-8', errors='replace'))
          except Exception:
              break
  # (进入现有主循环 → ⑦)
  ```
  新会话（sessionID 未命中）忽略 `replay` 参数，行为不变。

#### 2. functions/term/static/term.js（前端，3 处小改）

- **buildSessionUI** 的 session 对象增加字段：`needReplay: false`。
- **restoreSessions**：为每个恢复构建的会话置 `s.needReplay = true`（fresh 空终端首次连接需要回放；一次性标志）。
- **connectWs**：构建 url 后 `if (session.needReplay) { url += '&replay=1'; }`；
- **handleControl** hello 分支：`session.needReplay = false;`（连接建立即消费，同页后续重连不再回放，避免画面重复）。

### 不改动

- resize 流程、心跳、指数退避重连、`_sealSocketAfterClose` 与防抢占守卫（上轮修复原样保留）；
- `outQueue`/`MAX_BACKLOG`/reaper 保活机制；
- 前端 `resumed=true` 不 reset 的现有逻辑（fresh 终端本为空，回放直接写入）。

## 假设与决策

| 决策 | 理由 |
|------|------|
| REPLAY_MAX = 512KB | 全屏 TUI 单帧数 KB，512KB 保尾部多帧必含当前屏；cmd 滚动区 512KB 足够；内存开销每会话 ≤0.5MB 可接受 |
| 不加锁 | 仅 `_reader` 单写者，CPython GIL 下 `append`/`pop(0)`/`list()` 原子，注释说明即可 |
| 回放仅限 `replay=1`（一次性） | 同页重连画面已在 xterm 实例中，靠 outQueue 差量补齐即可，回放会重复 |
| 用户已确认路线 | AskUserQuestion 三选一，用户选"服务端回放缓冲（推荐）" |

## 验证

1. `py_compile` 校验 term_bp.py。
2. 启动 18080 测试实例（sys.path 注入 + `discoverBuiltinBlueprints`/`loadAndRegisterPlugins`/`initSockInstances`，`threaded=True`，无 reloader）。
3. 浏览器代理场景：
   - **S1 历史重建**：新建 cmd → 执行 `echo test001`、`dir`、`ver` 造输出 → 整页刷新 → 断言恢复后终端文本含 `test001`（历史输出已回放）；
   - **S2 TUI 场景**：powershell 会话刷新恢复后画面非空（含提示符）；
   - **S3 鼠标交互回归（问题 B）**：刷新恢复后，`browser_evaluate` 对 `.xterm-screen` 中心派发 `mousedown/mouseup` 与 `wheel` 事件，断言：(a) 点击后 `.xterm` 获得 `focused` 类；(b) 派发 wheel 后 `.xterm-viewport.scrollTop` 发生变化（scrollback 非空时）；(c) 键盘输入仍通（输入字符后屏幕回显）；
   - **S4 同页切换回归**：两会话间切换再切回 → 画面保留、切换期间输出补齐、无重复；
   - **S5 回归**：全程无 `Invalid frame header`/1006，服务端日志无异常关闭。
4. 用户真实环境（端口 80）复测：刷新恢复后画面完整、可点击、可滚动。

## 收尾步：写报告（验证通过后，用户要求）

项目根目录写 `REPORT-term-ws.md`：覆盖两个修复——(1) Invalid frame header 根因链路与 seal/守卫方案、前后对照验证；(2) 回放缓冲方案、竞态设计、S1-S5 验证结论。完成后随回放改动一并提交推送（第二次 push）。

## 问题 B 残余风险与后备诊断

回放应同时恢复鼠标模式与滚动区内容；若 S3 仍失败，按以下决策树诊断（同一验证会话内用 `browser_evaluate` 检查，无需二次规划）：
- `.xterm-screen` 的 boundingRect 与 `.session-terminal` 不符（rows 尺寸错乱）→ 修 `fit()` 时机（可见后再 fit + fit 后才发 resize）；
- 点击命中非 `.xterm` 元素（`elementFromPoint` 显示遮挡）→ 查层级/遮挡元素并修 z-index；
- `.xterm-viewport` scrollTop 无变化且 scrollback 为空 → 属空缓冲滚动的固有行为，回放后应消失，无需处理。
