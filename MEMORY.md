# RemoteConnecter — AI Agent 长期维护记忆

> 本文件为 AI 助手维护本项目时的长期参考。每次改动后请更新"当前状态"与"历史改动"。
> 最后更新：2026-10-24

---

## 一、项目概况

**项目名**：RemoteConnecter（机房远程管理 / 监控系统）

**形态**：Flask 后端 + 浏览器控制终端，打包为单文件 exe 部署在机房电脑上，通过浏览器（局域网/内网穿透）远程管理。

**当前版本**：`v1.7-beta.1`（仓库已提交版；main 最新 `3d6de69`，git tag 最新 `v1.7-beta.1`。工作区另有**未提交**改动：`utils.py` VERSION 已改 `v1.7.1-beta.1`、build.cmd、plugins/proxy 调整）

**技术栈**：
- 后端：Python 3.9（`python39/` 内嵌环境）、Flask 3.1.2、flask_sock（WebSocket）、pywinpty（ConPTY 终端）、pygame（音频播放）、Pillow/pyautogui（屏幕控制）
- 前端：原生 HTML/JS + jQuery + xterm.js 5.3.0（本地化，`functions/term/static/`），无构建工具
- 打包：PyInstaller 6.15.0（`python39\python.exe -m PyInstaller`），UPX 压缩
- 日志：自研 `Logcat.py`（根目录）

**Git 远程**：
- `origin` = GitHub（分支 main / Win7）
- `gitee` = Gitee（分支 main / master）

---

## 二、当前项目结构

```
RemoteConnecter/
├── RemoteConnecter.py      # 主入口：仅 DPI 设置 + Flask 装配 + 公共静态路由 + 宿主串联启动（44 行）
├── hosts/                  # ★ 宿主层（v1.6-beta1 抽离）
│   ├── blueprintHost.py    # 蓝图宿主：discoverBuiltinBlueprints / registerModuleBlueprints / initSockInstances
│   └── pluginHost.py       # 插件宿主：getPluginDirs / loadPlugins / loadPluginFile / loadAndRegisterPlugins
├── plugins/                # 官方插件（sample/proxy，已入库随 exe 内嵌；proxy/lib 为未跟踪私有依赖）
├── utils.py                # 工具库：VERSION、resourcePath、isPackaged、_MEI 清理、文件浏览、自动更新
├── Logcat.py               # 彩色日志模块（info/warn/error/debug）
├── functions/              # ★ 业务模块集合（自动扫描）
│   ├── __init__.py
│   ├── main/               # 主页 + 文件管理（main_bp.py + file_bp.py）
│   ├── screen/             # 屏幕截图/推流/远程控制（screen_bp.py）
│   ├── term/               # 终端 WebSocket/ConPTY（term_bp.py + sock）
│   ├── bilimusic/          # B站音乐（bilimusic_bp.py + bilimusic.py API）
│   ├── update/             # 自动更新（update_bp.py）
│   └── shared/static/      # 公共静态资源（jquery 等）
├── bin/ffmpeg.exe          # 转码二进制（m4a→wav）
├── upx/                    # UPX 压缩工具
├── python39/               # 内嵌 Python 3.9 环境（打包用）
├── Installer/              # 安装器（含 RunAsAdministrator.cmd、sys32 安装脚本）
├── build.cmd               # 唯一打包入口（纯 cmd，自动扫描蓝图/数据；生产隐藏黑窗，传 --show-console 调试）
├── 更新说明.md             # 各版本更新日志
└── MEMORY.md               # 本文件
```

---

## 三、核心架构约定（新增功能必读）

### 1. 宿主层（v1.6-beta1 起的结构）
主入口只做装配，发现/注册逻辑在 `hosts/` 包：
- `hosts/blueprintHost.py` — 内置蓝图宿主：`discoverBuiltinBlueprints(app)` 用 pkgutil 扫描 `functions/`（PYZ 兼容）返回 sock 列表；`registerModuleBlueprints(app, module)` 注册 `*_bp` 变量并收集 sock；`initSockInstances(app, sockInstances)` 统一 `init_app`
- `hosts/pluginHost.py` — 插件宿主：`getPluginDirs()` 返回四级目录列表、`loadPlugins(pluginDirs)` 收集+加载、`loadAndRegisterPlugins(app)` 一站式入口（返回插件 sock 列表）
- 主入口启动串联：`sockInstances = discoverBuiltinBlueprints(app)` → `sockInstances += loadAndRegisterPlugins(app)` → `initSockInstances(app, sockInstances)`，整体 try/except 兜底不阻断启动
- **打包注意**：`build.cmd` 必须显式 `--hidden-import hosts.blueprintHost hosts.pluginHost`

### 2. 蓝图自动扫描注册（内置模块）
`discoverBuiltinBlueprints` 扫描 `functions/` 下所有业务包中的 `*_bp.py` 并自动注册。

**新增功能只需**：
1. 在 `functions/` 下新建目录 `functions/xxx/`
2. 创建 `functions/xxx/xxx_bp.py`，定义 `xxx_bp = Blueprint(...)`
3. **主入口与 hosts 零改动**

**硬性约定**：
- 蓝图模块文件必须命名 `*_bp.py`（否则不扫描）
- 蓝图变量必须命名 `*_bp`（如 `main_bp`），否则不注册
- WebSocket 变量必须命名 `sock`（如 term 的 `Sock()`），统一 `init_app`
- `shared` 目录无 `_bp.py`，会被自然跳过（只能放公共静态资源）

### 3. 插件系统（v1.6 新增，plugin.json 清单驱动）

**四级目录**（`getPluginDirs()` 返回顺序 = 优先级从低到高，同 id 高层覆盖低层）：
| 层级 | 路径 | 说明 |
|---|---|---|
| 自带 | `resourcePath('plugins')`（打包态 `_MEI/plugins`，开发态项目根 `plugins/`） | 随 exe 分发的官方插件 |
| 程序级 | 打包态 exe 同级 `plugins/`（开发态与自带层同路径） | 用户在 exe 旁放置 |
| 全局级 | `%PROGRAMDATA%\RemoteConnecter\plugins\` | 机器级共享（机房部署） |
| 用户级 | `%APPDATA%\RemoteConnecter\plugins\` | 用户私有 |

**插件结构**：每个插件一个目录，必须含 `plugin.json`（`{"id": "xxx", "entry": "xxx_bp.py"}`，可选 `"lib": "lib"` 私有依赖目录）；无清单即跳过。已实测：全局级覆盖程序级、用户级覆盖全局级均生效。

**插件编写契约**：
- 入口模块内蓝图变量以 `_bp` 结尾，主程序自动注册
- WebSocket 变量固定命名 `sock`，自动 `init_app`
- **蓝图注册名必须带 id**：`Blueprint(f'{pluginID}_bp', ...)`，路由路径带 id 前缀 `f'/{pluginID}/...'`，静态路径 `static_url_path=f'/{pluginID}/static'`——蓝图名/endpoint/路由三层防撞（实测视图函数同名不冲突，endpoint 键是 `蓝图名.函数名`）
- 插件内读清单/文件必须用 `__file__` 锚定（`os.path.dirname(os.path.abspath(__file__))`），**禁止相对路径 open**（CWD 随启动方式漂移，双击 exe 时会找不到文件）
- 禁止相对导入；主进程已有库直接 import，私有依赖放 `lib/`（自动 `sys.path.insert(0, ...)` 且不移除，支持延迟 import）
- 清单读取用 `encoding='utf-8-sig'`（兼容记事本 BOM）

**容错**：单插件失败仅记 ERROR（含 `rcplugin_<id>` 的 `sys.modules` 注册），不阻断主程序启动；`plugins` 不存在静默跳过，存在但非目录告警。

**打包官方插件（已实施 2026-09-27）**：未另建 `officialPlugins/` 目录——仓库 `plugins/`（sample/proxy）直接 `--add-data "plugins;plugins"` 内嵌进 exe 自带层 `_MEI/plugins`，随启动版本同步逻辑生效。

### 4. 蓝图自带 template/static
每个业务蓝图声明 `template_folder='templates'`、`static_folder='static'`，前端文件放各自业务目录内，不走全局 static。

### 5. 路由约定
- 无 url_prefix 的短路由：`/`（main 主页）、`/terminal`（term）、`/screenshot`（screen）、`/bilimusic`（bilimusic）、`/update`（update）、`/download`、`/upload`（file）
- 全部蓝图统一无 `url_prefix`，路由一律写显式全路径
- 静态资源：`/shared/static/...`（公共）、`/main/static/...`、`/screen/static/...`、`/term/static/...`、`/bilimusic/static/...`、`/update/static/...`（业务）
- 根路由 `/` = 主页（main_bp 直挂，无重定向）

### 6. 命名规范（重要！用户强约束）
- **所有变量、函数、对象属性必须小驼峰（lower camelCase）**：`userName`、`getUserId`、`isLoggedIn`、`apiEndpoint`
- 唯一例外：类名/构造函数用 PascalCase（`Logcat`、`_PipeProcess`）
- 常量用全大写（`VERSION`、`FFMPEG_PATH`）
- 禁止 snake_case、禁止非类名 PascalCase

### 7. 资源路径
- 所有动态资源（模板、静态、二进制）用 `resourcePath('functions/xxx/...')`（兼容 PyInstaller `_MEIPASS`）
- ffmpeg 在 `resourcePath('bin/ffmpeg.exe')`
- exe/程序所在目录：打包态 `os.path.dirname(sys.executable)`，开发态 `os.path.dirname(os.path.abspath(__file__))`（onefile 下 `__file__` 指向临时 `_MEI`，只有 `sys.executable` 指向真实 exe）

---

## 四、当前状态（v1.6-beta3）

### 已完成
- ✅ 业务模块移入 `functions/`，蓝图自动扫描注册
- ✅ 主页直挂根路径 `/`（原 `/main/`，通过 `static_url_path='/main/static'` 保留静态资源 URL 不变）
- ✅ term/screen 路由缩短为 `/terminal`、`/screenshot`
- ✅ 无用文件清理（design.html、control.html、input-panel.js、claudecode.cmd、ffmpeg-mini.exe）
- ✅ 构建脚本 `--add-data` 全路径更新
- ✅ _MEI 残留自动清理（`utils.cleanupMeiFolders` 在启动入口调用，删除探测方案）
- ✅ CSS 内联样式抽离为独立文件 + `common.css` 公共基础样式
- ✅ 终端 xterm.js 本地化（xterm@5.3.0 + xterm-addon-fit@0.8.0 → `functions/term/static/`，去掉 CDN 依赖）
- ✅ 终端 resize 重构：`term.onResize` 与 `window resize` 合并为单一 `sendResize()`；连接时 `ws.onopen` 立即同步初始尺寸（修复首次 resize 丢失 bug）
- ✅ `file-btn` → `action-btn` CSS 类名泛化；主页「打开全屏终端」按钮新标签页打开 `/terminal`
- ✅ v1.5.3：终端 Termux 风格控制键（Ctrl+C/方向键/Tab/ESC，黑色方形图标键，手机端 40px 键位、窄屏不隐藏）
- ✅ v1.5.3：首页按网卡列出全部 IPv4（169.254 划线弱化并移至末尾）；修复 IP 链接被 Jinja 转义失效（`|safe`）
- ✅ v1.6-beta1：插件系统上线（四级目录 + plugin.json 清单 + 四类容错），全链路实测通过（覆盖优先级、lib 依赖、损坏清单隔离）
- ✅ v1.6-beta3：`getPluginDirs` 目录过滤统一为尾部列表推导；版本号 v1.6-beta3
- ✅ v1.6（`142d50b`）：宿主抽离——`hosts/` 包（blueprintHost + pluginHost），主入口瘦身至 44 行；25 条路由全量测试通过；build-product.cmd 补 hosts hidden-import
- ✅ MEMORY.md 整合插件系统/宿主抽离全部经验；删除 `.trae/documents/` 计划文档与 `.claude/`（2026-09-26）
- ✅ **v1.6-beta3 打包态全量验证（2026-09-26）**：build-product.cmd 打包成功（exe 约 20.6MB）；exe 同级放 `plugins/sample`+`plugins/proxy`，23/23 路由全过（15 条内置蓝图 + MJPEG 流 HEAD 200 + 4 条插件路由 + `/shared/static/common.css` + POST 路由存在性 405/400/415）；首页确认显示 `v1.6-beta3`；reloader 双进程在 exe 下同样生效（3 进程：onefile 父 + reloader 父子）
- ✅ **v1.6-beta3 终端控制键增强（2026-09-27，`b01e07f`）**：新增 Enter 控制键（svgrepo 533683 Return 形箭头，发 `\r`）；TAB/ESC 改"框+文字"SVG 样式（文字 6.5 号 Consolas）；单击 `#status` 状态文字切换 `#control-keys` 显隐，localStorage 键 `showControlKeys` 记忆（标记挂 `#control-keys` 自身，避免被 `setStatus` 重写 className 清掉）；增量重打包验证通过（exe 20.1MB）
- ✅ **官方插件内嵌打包（2026-09-27）**：`plugins/` 直接 `--add-data "plugins;plugins"` 打进 exe 自带层 `_MEI/plugins`，开发/生产两个 build 脚本都加、不区分环境；版本号转正 `v1.6`（待打包验证自带层加载）
- ✅ **打包脚本统一为 build.cmd 纯 cmd 自动扫描（2026-09-29）**：删 `build-product.cmd`/`build-develop.cmd`/残留 `RemoteConnecter.spec`，单一 `build.cmd`（默认生产隐藏黑窗，`--show-console` 调试）；模块侧 `for /r functions *_bp.py` 循环自动生成 `--hidden-import`（剥 `%~dp0` 前缀 + `\`→`.`），数据侧 `for /d` 循环自动生成 `--add-data`；新增业务零改动（临时 functions/demo 实测：PYZ 自动收 `functions.demo.demo_bp` 且 `/demo` 200，还原后基线 exe 20.10MB、10 条冒烟路由全 200）；**实测修正**：`--collect-submodules functions` 在 spec 求值时返回 0（嵌入式 `_pth` 限制，手动插 sys.path 才返回 15），旧脚本"可用"是缓存假象
- ✅ **远程终端多终端 + 断线重连（2026-10-01，分支 `feat/term-multi-reconnect`）**：引入 `TermSession` 会话对象 + 全局 `sessionMap` 注册表，将"WS 生命周期==进程生命周期"解耦为"会话独立生命周期"；WS 断开→`_detach` 保活（`DETACH_TIMEOUT` 宽限，初版 300s，2026-10-17 延至 7200s 见下，`_sessionReaper` 10s 扫描回收，`MAX_BACKLOG=20000` 输出队列封顶丢最旧），重连带 `session` 参数 attach 复用进程恢复现场。帧协议扩展：新增 `hello` 帧（attach 后第一帧，含 `resumed` 决定前端是否 reset）、`close` 帧（前→后显式杀会话）、启用 `ping`/`pong` 心跳（前端 15s）。前端 `term.js` 单例改会话数组，新增侧边栏（`#sidebar` 会话列表，`#sidebar-toggle` 切换 + localStorage 记忆）、切前台断开旧 WS 保活、仅前台指数退避重连（`1000*2^(n-1)` 封顶 30s）。`term.html` 加 `#sidebar`+`#main` 包裹，预设按钮改 `createSession(...)`、`#connect` 改"新建"；`term.css` 改 row 布局 + 侧边栏/会话项/窄屏覆盖层样式。**整页刷新不丢终端**：新增 `GET /terminal/api/sessions`（`listSessions`）返回存活会话 `{id,cmd,attached}`，前端 `buildSessionUI` 抽离（供新建/恢复复用）+ `restoreSessions` 在页面加载时拉取列表重建终端并 `switchSession` 重连恢复（`sessionID` 预填走 attach）。架构硬约束全程保留：pywinpty 线程亲和（spawn/read 同线程在 `_reader`）、ws.send 全收敛 WS 主线程、`b'0011Ignore'` 空串≠EOF、Windows write 收 str。**关键启动约束：`app.run` 必须 `threaded=True`**——多会话架构要求并发处理多个连接/请求；不能用 `processes>1`(fork)，因 `sessionMap` 是进程内内存表、winpty 句柄不可跨进程共享。**"Invalid frame header" 真因（2026-10-14 定位）**：flask_sock werkzeug 模式下 handler 返回普通 200 Response，werkzeug `execute()` teardown 会向已升级 socket 补写 `HTTP/1.1 200 OK` 头；浏览器 CLOSING 状态仍在读帧（同页抢占/刷新交接窗口），该字节被解析为非法帧。修复 = `term_bp.py` 的 `_sealSocketAfterClose`（发 close 帧后 `shutdown(SHUT_WR)`，teardown 写入必然 BrokenPipeError 被其 `connection_dropped` 分支静默吞掉）+ 前端 `connectWs` 防抢占守卫（同会话 `readyState<=2` 禁止重复建连，否则服务端失权旧连接触发本 bug）。GetDiagnostics 4 文件全通过
- ✅ **刷新恢复画面回放缓冲（2026-10-14，同分支）**：刷新后新 xterm 丢失全部转义序列状态（历史输出/备用屏/鼠标模式 `?1000h`）→ 画面空白 + 鼠标点击/滚轮失效同源。修复：`TermSession.replayBuf`（`REPLAY_MAX=512KB` 滚动缓冲，`enqueueOut` 先 append replayBuf 再 put outQueue）+ `wsTerminal` 重连带 `&replay=1` 时按**快照→清空 outQueue→hello→回放→主循环**顺序（不重不丢；快照与清空间新到的块已入快照、清空后新到的只走队列）；前端一次性标志 `needReplay`（restoreSessions 恢复的 fresh 空终端置 true，hello 到达即消费，同页重连不回放防画面重复）。验证：Python WS 客户端确定性 PASS（回显行恰出现 1 次）+ 浏览器端到端（40KB dir /s 历史完整重建、markOK123 计数=2 无重复、scrollTop 可滚、term.focus() 聚焦正常、控制台零报错）。**测试教训**：`dir /s` 在用户目录跑数分钟会吞掉后续 echo（命令排队非 bug）；多会话页面取画面必须用 `activeSession.term.buffer.active.getLine(i).translateToString(true)`，`querySelector('.xterm-rows')` 会取错 DOM；浏览器代理验证终端输入用 `activeSession.ws.send('cmd\r\n')` 代替合成键盘事件。详见 REPORT-term-ws.md
- ✅ **v1.7-beta.1 版本号规范化（2026-10-14~17，`43805b0`）**：`v1.7-beta1`→`v1.7-beta.1`（SemVer 预发布格式），改动提交到功能分支后 `git tag -f v1.7-beta.1 43805b0` 强移 tag 并 `push -f` 推 tag（`git tag -f` 精准操作单标签，历史标签全保留）；当时 main 按用户决定停留 v1.6，后经 GitHub PR 合入 main（`3472731`）。CHANGELOG.md 曾创建后按用户要求删除，**更新日志不入库**，发版用 GitHub Release
- ✅ **DETACH_TIMEOUT 300→7200（2026-10-17，`8b241c6`）**：用户实测后台任务 5 分钟即被 `_sessionReaper` 杀进程；延至 7200s（2 小时）支持长耗时后台执行
- ✅ **侧边栏覆盖层移植（2026-10-22，分支 `feat/sidebar-overlay`，已合入 main `3d6de69`）**：探测 factorization.top/rsc 的实现模式（`<aside>` fixed + `translateX` 滑入滑出 + 独立遮罩 div，class 切换驱动）移植到本项目：`term.html` 加 `#sidebar-overlay`；`term.css` 将 `#sidebar` 从 flex 推挤布局改为 fixed 覆盖层（`translateX(-100%)→0`，0.25s ease），遮罩淡入淡出，暗色主题半透明+`backdrop-filter: blur(8px)`，删 640px 媒体查询里冗余 fixed 规则；`term.js` 新增 `setSidebarOpen()` 统一同步侧边栏/遮罩 class 与 localStorage 偏好，点遮罩收起；**☰ 展开按钮全视口宽度始终显示**（用户要求，未引入源站 768px 显隐断点）
- ✅ **侧边栏 X 关闭按钮（2026-10-22，`552bd57`→`d74e808` 回退→`f824fcd` 重实现）**：侧边栏标题"终端"改为 X（SVG）关闭按钮 `#sidebar-close`（32px 圆角，hover 变红 `#f85149`），`#sidebar-head` 加 `gap:8px`。**教训**：首次实现破坏界面布局，用户要求回退到覆盖层重写版（d74e808 整体还原到 519243b），先推送回退态再增量重实现——破坏性前端改动应小步提交
- ✅ **打包态全量浏览器测试 T1-T6 全过（2026-10-22，dist exe + 浏览器代理）**：T1 会话命令 echo / T2 刷新恢复+回放（`needReplay` 一次性消费）/ T3 快速刷新×3 无 Invalid frame header 与 1006 / T4 多会话前台 connected 后台 detached / T5 侧边栏覆盖层全交互（fixed 定位、遮罩 class 同步、X 按钮与点遮罩收起均生效）/ T6 控制台健康。**踩坑**：旧 exe 孤儿进程残留占 80 端口 → 新实例 500 `TemplateNotFound: term.html`（旧 `_MEI` 无新模板，具迷惑性）——打包测试前必须 `taskkill /IM RemoteConnecter.exe /F` 全清再启动
- ✅ **分支收尾（2026-10-23）**：临时分支本地+远端全删（`feat/term-multi-reconnect` 随 GitHub PR 合并被远端自动删、`feat/sidebar-overlay` 手动删、残留 worktree-agent-* 分支清理），仅剩 `main` 与 `Win7`；工作区未提交：`utils.py`（v1.7.1-beta.1）、`build.cmd`、`plugins/proxy/*`、`functions/update/repoUpdate.py` 草稿、`.trae/`
- ✅ **Code 插件 `/code`（2026-10-23，`c0c136c` + 本次 UI 修复）**：VS Code 风格工作台（无 titlebar、活动栏、资源管理器、欢迎页水印、状态栏、终端面板）；Monaco 多标签、Markdown 预览、F5、菜单/命令面板/快捷键；`/code/api/workspaces` 注册根目录后仅传 `workspaceId + 相对路径`，`rc_code_fs.py` 负责沙箱/编码/EOL/ETag/原子保存；内嵌终端复用 `/term` WS，`mode=single` 断线即杀不恢复，multi 保持原行为。**关键坑**：Monaco 的 `editor.main.css` 自带全局 `.codicon[class*=codicon-] { font:16px/1 codicon }`，加载后会覆盖 `code.css` 的图标尺寸/字体，导致刷新时水印与图标突变；UI 图标统一加 `body` 前缀提高优先级，并使用独立 `rc-codicon` 字体，Monaco 内部保留 `codicon`。状态栏不显示运行时列表，运行时仅用于 F5/终端。

### 分支结构（2026-10-24 重组）
- `feat/app-improvements`：主程序非插件功能合集（term 多模式/版本号/打包修复/.trae 文档/repoUpdate/debug 门控/文件列表/屏幕键盘/MEMORY），基于 main
- `feat/auto-dev-2`：屏幕鼠标增强 + process 插件（原基于 temp/code-editor，该分支已删，插件源码权威在 RemoteVSCode `e6554d8`）
- ~~`temp/code-editor`~~ **已删除**（2026-10-24）：plugins/code 部分完整镜像于 github.com/mc-lhz/RemoteVSCode，非插件部分抽至 feat/app-improvements，删除前三重验证通过

### 进行中 / 待办

#### 产品功能（来源：GitHub release v1.5.3-beta2 的 Todo List，2 项已完成）
- ✅ 文件列表改为仅显示文件名 + 顶部路径栏（2026-10-24，`81b8b99`）：`file-manager.js` 列表项从完整路径改 basename（保留原大小写，盘符根显示 `C:`），完整路径移 `data-path`（点击改读 dataset，修复含空格/中文路径的文件打开 URL 未编码问题），新增 `#current-path` 路径栏随目录切换
- ✅ **实时屏幕"部分按键不可用"修复（2026-10-24，`7679fbe`）**：四类根因——①含 `+` 的字符被组合键 `split('+')` 撕碎（改逐键多参数 `keys=a&keys=%2B`，后端 `getlist`，旧单参数格式兼容）；②孤立修饰键从不转发（单按 Shift 切输入法/单按 Alt 呼出菜单栏/Ctrl+Shift 切输入法全失效——前端补修饰键状态机：纯修饰组合在第二键按下瞬间发送、孤立修饰键在松开瞬间补发）；③`ArrowLeft` 被映射成后端不认识的 `arrowleft`，pynput 当普通字符逐字打出（改映射 `left/up/down/right`）；④中文 IME 组字阶段 `e.key='Process'` 与死键 `'Dead'` 被当普通键发送（过滤+提示），另补 AltGraph→alt_gr、ContextMenu→menu。**测试方式**：后端 mock 控制器验证按键序列（绝不真实注入按键）、前端 stub `$.get` 验证映射/状态机
- ✅ **Code 插件全工作区替换（2026-10-24，`ed5b797`）**：`POST /code/api/fs/replace` 与搜索同语义，逐文件读取→替换→带 etag 原子写回（并发冲突跳过计入 conflicts、脏标签不重载、替换内容按字面量）；搜索面板替换行 + 全部替换按钮 + 危险二次确认，完成后自动重载受影响标签/刷新树/重搜；Ctrl+H 聚焦替换框，搜索视图自动预填编辑器选中文本
- ⏳ 优化实时屏幕，提升公网访问流畅性
- ✅ 修复实时屏幕部分按键不可用的 Bug（2026-10-24，`7679fbe`，见上方已完成）
- ✅ 远程终端多终端支持 + 断线重连（2026-10-01，分支 `feat/term-multi-reconnect`，见上方已完成）
- ⏳ 终端图标改为动态获取，不再使用静态资源
- ✅ 加入以 Monaco Editor 为核心的代码编辑器（2026-10-23，`/code`，见上方）
- ✅ 加入插件功能（v1.6-beta1 已实现）
- ✅ 加入 proxy 功能（proxy 插件已存在并验证）

#### 工程/打包
- ✅ 官方插件内嵌打包：直接把仓库 `plugins/` 用 `--add-data "plugins;plugins"` 打进 exe 自带层（`_MEI/plugins`），开发/生产两个 build 脚本都加、不区分环境；**已打包验证**（dist 不放同级 plugins，`/sample`、`/sample/sample`、`/sample/static/sample.js`、`/proxy` 全 200，确认命中 `_MEI` 自带层）
- ✅ 官方插件仓库独立化（2026-10-23）：`RemoteVSCode` 仅含 `plugins/code` 解包内容（根目录 `code_bp.py`/`lib/`/`static/`/`templates/`/`plugin.json`，单提交 `5284b66`）；`RemoteOffice` 改为仅含 `plugins/office` 解包内容（根目录 `office_bp.py`/`static/`/`templates/`/`plugin.json`，单提交 `7e881ad`，force-push 覆盖旧全量应用 main `250b4e8`）；旧 RemoteOffice 全量历史已备份到 `%TEMP%\opencode\RemoteOffice-backup` 与 `RemoteOffice-latest-preoverwrite-250b4e8.bundle`
- ✅ **Office 插件 x2t WASM 加载失败修复（2026-10-24，RemoteOffice `b90aca8`）**：纯 HTTP（如 `http://192.168.0.107:8765`）下 Chrome/Edge 请求头只有 `Accept-Encoding: gzip, deflate`（br 仅在 HTTPS 连接上声明），服务端却无条件给 `x2t.wasm.br` 标 `Content-Encoding: br` → 浏览器判 `ERR_CONTENT_DECODING_FAILED`（net_error -330），对外表现为 `fetch() TypeError: Failed to fetch`、`X2T module failed to instantiate: Failed to fetch`、文档打不开。**"curl 正常但浏览器 fetch 失败"是该类编码头错误的典型特征**（curl 不校验未声明的 Content-Encoding），用 Edge `--log-net-log` 抓网络日志定位。修复：`office_bp.py` 预压缩资产（`.br/.gz`）按客户端 `Accept-Encoding` 门控，未声明对应编码时回退同名未压缩副本（`/office/app/` 非模板文件统一走 `serveDistFile`，此前该路由不经编码门控），无副本返回 415。**dist 侧需预置 `sdkjs/common/wasm/x2t/x2t.wasm`**（由 `x2t.wasm.br` brotli 解压出的 42,111,200 字节裸 wasm，已生成于 `%PROGRAMDATA%\RemoteConnecter\office\dist`；重新部署 dist 时需重新生成）。Edge headless 实测文档打开正常、wasm 编译通过。本地 8765 测试服务现由 `%TEMP%\opencode\RemoteOffice-backup` 运行（`run_office_test.py` 已改绑 `0.0.0.0`）
- ✅ **Code 插件全工作区搜索 + Ctrl+P 快速打开（2026-10-24，`1c07f04`/`065c876`）**：`GET /code/api/fs/search`（按行匹配、大小写/正则开关、跳过隐藏目录与 node_modules/__pycache__/符号链接、单文件 512KB/100 命中与总命中 500 截断、二进制经 decodeText 拒绝、返回 previewCol/previewLength 供高亮）+ `GET /code/api/fs/list`（全工作区文件名列表）；侧栏拆"资源管理器/搜索"双视图（活动栏切换、再点收起），搜索面板防抖自动搜索 + Aa/.*/刷新/清空按钮 + 按文件分组高亮结果，点击经 `CodeEditor.revealPosition(path,line,col)` 跳转；Ctrl+Shift+F 开搜索、Ctrl+P 快速打开（模糊子序列打分，文件列表 15s 缓存）。F5 UI 实测补齐（Python 脏保存→运行→落盘、Node、控制台零错误，全 PASS）；另有 Ctrl+G 跳转到行（`b5167a1`）。**回归脚本坑（已修复，现 22/22）**：`code_ui_regression.py` 的 save 用例曾用 `monaco.editor.getModels()[0]` 取模型，多标签时索引指向先打开的文件（写错 model + saveActive 对干净活动标签直接 true）——已改为按 `m.uri.path.endsWith()` 定位；另需在控制台检查中排除用例预清理 404 与 Monaco 内部无害噪音 `Uncaught _: Canceled`（模型/标签快速切换时被取消的 promise）
- ✅ **repoUpdate 修复 + 生产关闭 debug/reloader（2026-10-24，`56b6e66`/`63ca014`）**：repoUpdate.py 修 `downloadUpdater` 未定义 `availableNodes`、`getRelease()` 返回值未用（现提取资产地址传入下载器）、去导入时 `os.chdir` 副作用、全请求加超时 + 流式下载 + MZ 头校验 + 临时文件原子替换（实测 11/16 节点可用、GitHub API 取到 v1.7.1）；`RemoteConnecter.py` 改 `isPackaged()` 时自动关 debug/reloader（frozen 下 reloader 双进程 + 调试器任意代码执行风险），开发态 `RC_DEBUG=0` 可临时关闭
- ⏳ `.gitignore` 插件策略待定：仓库 `plugins/`（sample/proxy）是官方插件需入库打包；若日后出现用户级/运行时生成的插件目录才需要忽略
- ⏳ `functions/update/repoUpdate.py`（未跟踪草稿）：仓库更新器，有 bug（`downloadUpdater` 引用未定义的 `availableNodes`，`getRelease()` 返回值未用）
- ✅ 生产环境关闭 `app.run` 的 debug/reloader（2026-10-24，`63ca014`）：`isPackaged()` 时自动关闭，开发态 `RC_DEBUG=0` 可临时关闭（原风险：frozen 下 reloader spawn 双进程、debug 调试器任意代码执行）
- ⏳ 构建时选择 ConPTY/WinPTY 后端（build-time-pty-backend-selection 方案已论证，未实施）：pywinpty 的 `PtyProcess.spawn(..., backend=Backend.WinPTY)` 可显式指定后端，同一份源码打 Win10/Win7 两个 exe

### 踩坑记录（打包/测试相关）
- **MJPEG 流路由测试陷阱**：`/screenshot/api/stream` 是无限流，`Invoke-WebRequest` 全量 GET 会一直读到连接关闭（实测读了 900MB+ 才超时）；全量路由测试必须改用 `HEAD` 请求验证状态码 + Content-Type
- **PowerShell 5.1 异常状态码**：`$_.Exception.Response.StatusCode` 直接 `[int]` 强转会报 `Cannot convert ... to System.Int32`（值是字符串如 '405'），需先 `[string]` 再转或取首段数字
- **PSReadLine 长命令渲染异常**：终端内联超长命令会触发 `ArgumentOutOfRangeException` 刷屏，不影响实际执行；稳妥做法是写临时 .ps1 用 `powershell -NoProfile -ExecutionPolicy Bypass -File` 执行，测完删除
- bilimusic 的 ffmpeg 路径：`FFMPEG_PATH = resourcePath('bin/ffmpeg.exe')` 在打包后解析为 `_MEIPASS/bin/ffmpeg.exe`。build 脚本 `--add-binary` 的目标目录必须与之一致：必须用 `bin\ffmpeg.exe;bin`（目标 `bin`），**不能**用 `bin\ffmpeg.exe;.`（目标根，会导致 ffmpeg 落在 `_MEIPASS/ffmpeg.exe`，代码找不到 → 回退系统 PATH → 学校电脑无 ffmpeg → 播放报 `[WinError 2] The system cannot find the file specified`）。两个 build 脚本（product/develop）均已改为 `;bin`。

---

## 五、历史重要改动记录

### v1.5.3-beta1 / beta2 / beta3（详见 更新说明.md）
- **xterm.js 本地化**：xterm@5.3.0 + xterm-addon-fit@0.8.0 下载至 `functions/term/static/`，`term.html` 改为本地 `/term/static/...` 引用，去掉 CDN（cf → jsdelivr 下载）
- **终端 resize 重构**：`term.html` 将 `term.onResize` 与 `window resize` 两个 handler 合并为单一 `sendResize()` 函数；连接时在 `ws.onopen` 中立即调用 `sendResize()` 同步初始尺寸（修复首次 resize 丢失 bug）
- **`file-btn` → `action-btn`**：CSS 类名泛化（更普适）；`index.html` 终端按钮改 `onclick="open('/terminal','_blank')"` 新标签页打开全屏终端
- **beta3 终端控制键**：Termux 风格黑色方形图标键（Ctrl+C/方向键/Tab/ESC），窄屏不隐藏，手机端 40px 键位
- **beta3 首页 IP**：按网卡列出 IPv4 + 169.254 划线置底；`{{ip|safe}}` 修复转义失效

### v1.6-beta1 ~ beta3 + 宿主抽离（`142d50b`）
- **插件系统**：四级目录（自带 resourcePath('plugins') → 程序级 exe 同级 → 全局级 %PROGRAMDATA% → 用户级 %APPDATA%），同 id 高层覆盖低层（用户级>全局>程序级，实测验证）；`plugin.json` 清单（id/entry 必填，lib 可选，utf-8-sig 兼容 BOM）；`importlib.util.spec_from_file_location` 显式路径加载绕过打包 `_pth` 限制，模块名 `rcplugin_<id>` 注册 sys.modules；单插件失败仅记日志不阻断启动
- **插件防撞契约**（实测结论）：蓝图注册名带 id（`f'{pluginID}_bp'`）+ 路由带 id 前缀后，视图函数同名不冲突（endpoint 键 = 蓝图名.函数名）；裸撞蓝图名 Flask 静默改名 `xxx (1)` 导致 url_for 歧义，必须避免
- **插件静态资源**：放插件目录 `static/`，蓝图 `static_url_path=f'/{id}/static'`；页面引用必须用插件自己的路径（主应用 `static_folder=None`，写 `/static/...` 会触发 RuntimeError: 'static_folder' must be set）
- **宿主抽离**：`hosts/` 包拆分蓝图宿主与插件宿主，主入口 195→44 行只留装配；`registerModuleBlueprints(app, module)` 供两宿主复用；全量 25 条路由回归通过

### v1.7-beta.1（tag `v1.7-beta.1`，经 GitHub PR 合入 main，现 main 顶 `3d6de69`）
- **多终端会话 + 断线重连 + 刷新恢复 + 画面回放**（`8213fdf`/`c66e88c`）：核心见"当前状态"2026-10-01/10-14 两条；根因专文 REPORT-term-ws.md
- **Invalid frame header 修复**：服务端 `_sealSocketAfterClose` + 前端 `connectWs` 防抢占守卫
- **DETACH_TIMEOUT 300→7200**（`8b241c6`）：后台任务 2 小时保活
- **侧边栏覆盖层移植 + X 关闭按钮**（`519243b`/`f824fcd`）：fixed 覆盖 + 遮罩 + 滑入动画 + X 收起
- **构建脚本统一 build.cmd、官方插件 plugins/ 入库内嵌**（`54b120b`/`cc2e487`）
- **合并/发版方式**：GitHub 网页 PR 合 main → 本地 ff 同步 → 侧边栏分支本地 merge 推送；tag `v1.7-beta.1` 已推远端；临时分支合并后全删

### v1.5.2（已合并 main）
- **修复屏幕控制鼠标失效**（beta1）：`screen-control.js` 的 `sendClick` 请求路径多带 `/screen` 前缀导致 404（v1.5-beta1 路由缩短时漏改），统一为 `/screenshot/api/control`。受影响版本 v1.5-beta1~v1.5.1，升级即可修复
- **修复终端回车连接不同步命令**（beta2）：输入框直接回车连接时先同步输入框内容到 `globalCmd`
- **修复 _MEI 清理双实例误删**（重要）：原独占打开探测（`CreateFileW shareMode=0`）检测不到运行实例已加载 DLL 的 image section 映射（实测可成功打开但删除被拒），双开时后启动实例误删先启动实例的模板数据 → TemplateError。改为**删除探测**：尝试删除目录内 `python3*.dll`，运行实例删除必被拒（无损跳过），死实例可删（目录随即 rmtree）。已知盲区（用户接受）：onefile 解压期 dll 已写出尚未映射的数秒窗口，不设年龄宽限

### v1.5.1（已合并 main）
- **版本号升至 v1.5.1**：`utils.py` 的 `VERSION` 由 `v1.5-beta1` 改为 `v1.5.1`
- **CSS 结构整理**：5 个业务模块（main/term/screen/bilimusic/update）的内联 `<style>` 抽离为各自 `static/*.css`，新增 `functions/shared/static/common.css` 收敛全局重置规则，各 HTML 改为外链引用，提升可维护性
- **_MEI 残留自动清理**：`utils.cleanupMeiFolders()` 在 `RemoteConnecter.py` 启动入口（`app.run` 之前）调用。背景：PyInstaller `-F` 单文件每次运行解压资源到 `%TEMP%\_MEI<随机数>`，进程被强杀/崩溃/更新替换时残留累积。仅打包环境生效，自身 `_MEIPASS` 经 normcase 比较跳过。（初版用独占打开探测，v1.5.2 修正为删除探测，见上）

### v1.5-beta1（refactor-business-structure 分支，已合并 main）
- 业务模块目录重构：`main/screen/term/bilimusic/update/shared` → `functions/`
- 蓝图自动扫描注册（`discoverAndRegisterBlueprints`）
- 路由缩短：`/term/terminal`→`/terminal`、`/screen/screenshot`→`/screenshot`
- 删除横屏词典笔适配（v1.4.4 之前，RemoveDictLandscape 分支已合并）
- 无用文件清理

### v1.4.4（已合并 main）
- **B站音乐转码优化**：MP3 → WAV 转码，用完整版 ffmpeg（5.51MB，UPX 后 2.55MB），转码速度 3.4s → 0.1s
- 背景：v1.4.3 曾用 ffmpeg-mini（2.04MB）转 MP3，实测奇慢（约 3.4s），回退完整版 ffmpeg + WAV 方案
- 教训：轻量 ffmpeg-mini 转 MP3 性能差，WAV 转码快且音质无损

### v1.4.5-beta1
- 新增 `Installer/RunAsAdministrator.cmd`（sys32 安装：复制 exe 到 System32 + HKCU 注册表自启 + 关闭防火墙 + 80 端口规则 + 杀进程覆盖）

### 早期关键修复（v1.2 ~ v1.4）
- **终端 ConPTY 稳定性**：pywinpty spawn/read 必须同线程（线程亲和性 bug → EOF）；`b'0011Ignore'` 忽略帧返回空 str 不等于 EOF；wsproto 并发 send 需主线程统一发送
- **Win7 兼容**：Python 3.8 在 Win7 缺 api-ms-win-core-path dll → 用 Python 3.7 打包；Win7 无 ConPTY → `Win7` 分支删除终端功能
- **打包 0xc0000142**：不得加 `-w`（windowed 子系统 ConPTY 崩溃），改用 console 子系统 + `--hide-console hide-early`
- **打包体积**：根因是被污染的 Python 环境引入冗余库，用干净环境打包
- **横屏词典笔适配**：已彻底删除（`@media (min-aspect-ratio: 2/1)` 布局 + `detectDeviceAndLayout` JS）

---

## 六、打包指南

```bat
:: 生产打包（-F 单文件 + 隐藏控制台 + UPX + 全资源，自动扫描蓝图）
build.cmd

:: 调试打包（保留控制台黑窗便于看日志）
build.cmd --show-console
```

**自动扫描机制（2026-09-29 重构，已实测验证）**：
- **模块侧**：`for /r functions %%f in (*_bp.py)` 循环，把每个 `_bp.py` 绝对路径剥掉 `%~dp0` 前缀、去 `.py`、`\` 转 `.`，生成 `--hidden-import functions.xxx.xxx_bp`；另固定补 `--hidden-import functions.shared` 与 `--hidden-import hosts.blueprintHost hosts.pluginHost`
- **数据侧**：`for /d %%p in (functions\*)` 循环，对存在的 `templates`/`static` 目录自动生成 `--add-data`（`%%~np` 取相对目录名，cmd 替换不认转义，用 `!rel:%~dp0=!` 剥前缀）
- **新增业务零改动**：建 `functions/<name>/<name>_bp.py`（含 templates/static）即可，build.cmd 不改（实测：临时加 functions/demo，PYZ 自动收 `functions.demo.demo_bp` 且 `/demo` 200）
- **`--collect-submodules functions` 不可用（实测修正）**：嵌入版 python39 的 `_pth` 限制 sys.path，**spec 求值时**（即使 cwd 是项目根）collect_submodules('functions') 返回 0 → PYZ 只剩 `functions` 包本身，6 个 _bp 全漏（exe 仅 11.5MB 而非 ~20MB）。手动 `sys.path.insert(0, 项目根)` 后同函数返回 15——说明"PyInstaller 分析期把项目根加入 sys.path"只对静态分析图生效，**对 spec 顶层 Python 代码求值不生效**。之前"build-develop.cmd 用 collect-submodules 构建正常"是旧缓存假象，已废弃该脚本
- 教训：`_bp` 依赖运行时 pkgutil 动态发现（pyi_rth_pkgutil），静态分析图不会自动收，**必须显式 hidden-import**

**关键点**：
- 用 `python39\python.exe`（内嵌 Python 3.9，干净环境，避免冗余库）
- **绝不能加 `-w`**（windowed 子系统会致 ConPTY 崩溃 0xc0000142），用 `--hide-console hide-early`
- `--add-data` 的源/目标路径必须与蓝图 root_path 匹配（`functions/xxx/templates` 等）；ffmpeg 必须落 `bin` 目标（`;bin` 而非 `;.`）
- `--collect-all winpty`（Cython 扩展用 hiddenimports 收集不到）
- `PYINSTALLER_CONFIG_DIR` 指向项目内 `.pyinstaller_cache`（规避沙箱拦截系统缓存目录）
- UPX 对个别 DLL 报 `NotCompressibleException` 是无害警告，可忽略
- 打包需在沙箱外执行
- onefile exe 启动需 5-8 秒解压，期间验证会误报 404；测试前确认 80 端口无残留进程（曾因 System32 下旧 exe 双绑端口返回过期 CSS）

---

## 七、已知问题 / 注意事项

- **Windows 文件占用探测**（_MEI 清理实测结论，2026-08-29）：对运行实例已加载的 DLL（image section 映射），独占打开（`CreateFileW shareMode=0`）和目录重命名**均探测不到**；**只有删除（`os.remove`）会被拒绝**——判定文件是否被运行实例占用必须用删除探测
- **Werkzeug reloader 双进程**（2026-09-26 实测确认）：`debug=True, use_reloader=True` 下整个脚本顶层代码执行两遍（父进程监视 + 子进程服务），插件加载/pygame 初始化/日志均出现两次属正常；打包 exe 同样生效（双份 _MEI 解压 + 交互式调试器安全风险），生产必须关闭
- 插件目录里的 `__pycache__` 会缓存 .pyc：更新插件代码若"改了没生效"，先删插件目录下 `__pycache__`
- `bilimusic`、`update` 的 `/` 页面路由带斜杠访问（`/bilimusic/`、`/update/`），不带斜杠会 308 重定向（浏览器自动跟随，功能正常）
- `file_bp` 无独立页面/JS，功能内嵌在 main 的 index.html，归属 `functions/main/`，不含 templates/static
- Installer 目录曾有一份重复 Logcat.py，注意与根目录保持一致
- Win7 分支与 main 分支功能不同（Win7 无终端），合并时需谨慎
- 远程仓库有 GitHub（origin）和 Gitee（gitee）两个，推送时注意目标

---

## 八、开发方向参考（用户曾探讨）

1. **监控/遥测**：实时性能监控、进程管理、软硬件清单、网络监控
2. **远程操作增强**：远程剪贴板、批量脚本分发、远程电源控制、UI 文件上传
3. **机房/教学管理**：课堂控制、定时任务、行为审计、电源/桌面策略
4. **系统/架构**：多客户端统一面板、告警推送、HTTPS + 内网穿透 + 二维码访问、移动端 PWA
5. **插件生态**（v1.6 基础已就绪）：官方插件库、插件管理页（启用/禁用/更新）、插件市场/远程分发

---

## 九、GitHub Releases 速查（2026-09-26 抓取）

- **v1.5.3-beta2**（Pre-release）：终端 Termux 风格控制键；**其中列出的 Todo List 即上方"产品功能待办"的来源**
- **v1.5.3-beta1**（Pre-release）：xterm.js 本地化去 CDN、resize 重构、`file-btn`→`action-btn`
- **v1.5.3**（正式版）：169.254 划线置底 + 控制键方形图标；release 声明插件功能已完成待下版正式发布
- **v1.6-beta1**（Pre-release）：插件系统核心（目录/清单/契约/容错完整文档）+ 首页网卡 IP 列表
- **v1.6-beta2**（Pre-release）：插件系统完善（四级目录覆盖、static/templates/lib、单插件失败不阻断）
- 发布地址：`https://github.com/mc-lhz/RemoteConnecter/releases`（gitee 同步）
- 发版惯例：beta 为 Pre-release，正式版不带 Pre 标记；CHANGELOG 含 新增/优化/修复/注意/升级说明 分段
