# RemoteConnecter — AI Agent 长期维护记忆

> 本文件为 AI 助手维护本项目时的长期参考。每次改动后请更新"当前状态"与"历史改动"。
> 最后更新：2026-09-26

---

## 一、项目概况

**项目名**：RemoteConnecter（机房远程管理 / 监控系统）

**形态**：Flask 后端 + 浏览器控制终端，打包为单文件 exe 部署在机房电脑上，通过浏览器（局域网/内网穿透）远程管理。

**当前版本**：`v1.6-beta3`（见 `utils.py` 的 `VERSION`；最新推送提交 `ab9c52d`；git tag 最新 `v1.6-beta2`，v1.6-beta3 尚未打 tag）

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
├── plugins/                # 运行时插件目录（不入库）；测试插件 sample/proxy
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
├── build-product.cmd       # 生产打包（-F + hide-console + UPX + 全资源 + hosts hidden-import）
├── build-develop.cmd       # 开发打包
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
- **打包注意**：`build-product.cmd` 必须显式 `--hidden-import hosts.blueprintHost hosts.pluginHost`

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

**打包官方插件（未实施）**：方案已定——仓库建 `officialPlugins/`，`--add-data "officialPlugins;plugins"` 内嵌 + `syncBuiltinPlugins()` 按 `plugin.json` 的 `version` 字段同步解压到程序级（需新增 version 字段与 `versionKey` 数字比较）。

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

### 进行中 / 待办

#### 产品功能（来源：GitHub release v1.5.3-beta2 的 Todo List，2 项已完成）
- ⏳ 文件列表改为仅显示文件名（顶部显示当前文件夹路径），不再显示完整路径
- ⏳ 优化实时屏幕，提升公网访问流畅性
- ⏳ 修复实时屏幕部分按键不可用的 Bug
- ⏳ 远程终端多终端支持 + 断线重连
- ⏳ 终端图标改为动态获取，不再使用静态资源
- ⏳ 加入以 Monaco Editor 为核心的代码编辑器
- ✅ 加入插件功能（v1.6-beta1 已实现）
- ✅ 加入 proxy 功能（proxy 插件已存在并验证）

#### 工程/打包
- ⏳ 官方插件打包方案（内嵌 `--add-data "officialPlugins;plugins"` + 启动时按 version 同步解压到程序级）已设计未实施
- ⏳ 官方插件内嵌（`_MEI/plugins` 依赖 `--add-data "officialPlugins;plugins"`，当前 build 脚本未加该行，打包后自带层静默缺失）；四级加载打包态已验证（程序级 exe 同级 plugins 实测生效，自带层待上述实施后验证）
- ⏳ `.gitignore` 缺 `plugins/`（运行时插件目录未忽略，有误入库风险）
- ⏳ `functions/update/repoUpdate.py`（未跟踪草稿）：仓库更新器，有 bug（`downloadUpdater` 引用未定义的 `availableNodes`，`getRelease()` 返回值未用）
- ⏳ 生产打包建议关闭 `app.run(debug=True, use_reloader=True)`（frozen 环境下 reloader 会 spawn 双进程：Werkzeug 父子模型导致整脚本执行两遍、插件加载两遍、exe 双份 _MEI 解压；debug=True 的交互式调试器还有任意代码执行风险）
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
:: 生产打包（-F 单文件 + 隐藏控制台 + UPX + 全资源）
build-product.cmd

:: 开发打包（保留控制台便于调试）
build-develop.cmd
```

**关键点**：
- 用 `python39\python.exe`（内嵌 Python 3.9，干净环境，避免冗余库）
- **绝不能加 `-w`**（windowed 子系统会致 ConPTY 崩溃 0xc0000142），用 `--hide-console hide-early`
- **禁止 `--collect-submodules functions`**：嵌入版 python39 的 `_pth` 限制 sys.path 且忽略 PYTHONPATH，spec 求值时 collect_submodules 返回空 → functions.* 全部漏出 PYZ（打包后 404）。必须逐业务模块显式 `--hidden-import functions.xxx.xxx_bp`；hosts 包同理（`--hidden-import hosts.blueprintHost hosts.pluginHost`）
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
