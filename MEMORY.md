# RemoteConnecter — AI Agent 长期维护记忆

> 本文件为 AI 助手维护本项目时的长期参考。每次改动后请更新"当前状态"与"历史改动"。
> 最后更新：2026-08-30

---

## 一、项目概况

**项目名**：RemoteConnecter（机房远程管理 / 监控系统）

**形态**：Flask 后端 + 浏览器控制终端，打包为单文件 exe 部署在机房电脑上，通过浏览器（局域网/内网穿透）远程管理。

**当前版本**：`v1.5.2-beta2`（见 `utils.py` 的 `VERSION`）

**技术栈**：
- 后端：Python 3.9（`python39/` 内嵌环境）、Flask 3.1.2、flask_sock（WebSocket）、pywinpty（ConPTY 终端）、pygame（音频播放）、Pillow/pyautogui（屏幕控制）
- 前端：原生 HTML/JS + jQuery，无构建工具
- 打包：PyInstaller 6.15.0（`python39\python.exe -m PyInstaller`），UPX 压缩
- 日志：自研 `Logcat.py`（根目录）

**Git 远程**：
- `origin` = GitHub（分支 main / Win7）
- `gitee` = Gitee（分支 main / master）

---

## 二、当前项目结构

```
RemoteConnecter/
├── RemoteConnecter.py      # 主入口：Flask app + 蓝图自动扫描注册
├── utils.py                # 工具库：VERSION、resourcePath、系统信息、文件浏览、自动更新
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
├── build-product.cmd       # 生产打包（-F + hide-console + UPX + 全资源）
├── build-develop.cmd       # 开发打包
├── 更新说明.md             # 各版本更新日志
└── MEMORY.md               # 本文件
```

---

## 三、核心架构约定（新增功能必读）

### 1. 蓝图自动扫描注册（关键！）
`RemoteConnecter.py` 的 `discoverAndRegisterBlueprints(app)` 会扫描 `functions/` 下所有业务包中的 `*_bp.py` 并自动注册。

**新增功能只需**：
1. 在 `functions/` 下新建目录 `functions/xxx/`
2. 创建 `functions/xxx/xxx_bp.py`，定义 `xxx_bp = Blueprint(...)`
3. **主入口 RemoteConnecter.py 零改动**

**硬性约定**：
- 蓝图模块文件必须命名 `*_bp.py`（否则不扫描）
- 蓝图变量必须命名 `*_bp`（如 `main_bp`），否则不注册
- WebSocket 变量必须命名 `sock`（如 term 的 `Sock()`），统一 `init_app`
- `shared` 目录无 `_bp.py`，会被自然跳过（只能放公共静态资源）

### 2. 蓝图自带 template/static
每个业务蓝图声明 `template_folder='templates'`、`static_folder='static'`，前端文件放各自业务目录内，不走全局 static。

### 3. 路由约定
- 无 url_prefix 的短路由：`/`（main 主页）、`/terminal`（term）、`/screenshot`（screen）、`/bilimusic`（bilimusic）、`/update`（update）、`/download`、`/upload`（file）
- 全部蓝图统一无 `url_prefix`，路由一律写显式全路径
- 静态资源：`/shared/static/...`（公共）、`/main/static/...`、`/screen/static/...`、`/term/static/...`、`/bilimusic/static/...`、`/update/static/...`（业务）
- 根路由 `/` = 主页（main_bp 直挂，无重定向）

### 4. 命名规范（重要！用户强约束）
- **所有变量、函数、对象属性必须小驼峰（lower camelCase）**：`userName`、`getUserId`、`isLoggedIn`、`apiEndpoint`
- 唯一例外：类名/构造函数用 PascalCase（`Logcat`、`_PipeProcess`）
- 常量用全大写（`VERSION`、`FFMPEG_PATH`）
- 禁止 snake_case、禁止非类名 PascalCase

### 5. 资源路径
- 所有动态资源（模板、静态、二进制）用 `resourcePath('functions/xxx/...')`（兼容 PyInstaller `_MEIPASS`）
- ffmpeg 在 `resourcePath('bin/ffmpeg.exe')`

---

## 四、当前状态（v1.5.2-beta2）

### 已完成
- ✅ 业务模块移入 `functions/`，蓝图自动扫描注册
- ✅ 主页直挂根路径 `/`（原 `/main/`，通过 `static_url_path='/main/static'` 保留静态资源 URL 不变）
- ✅ term/screen 路由缩短为 `/terminal`、`/screenshot`
- ✅ 无用文件清理（design.html、control.html、input-panel.js、claudecode.cmd、ffmpeg-mini.exe）
- ✅ 构建脚本 `--add-data` 全路径更新
- ✅ _MEI 残留自动清理（`utils.cleanupMeiFolders` 在启动入口调用，删除探测方案）
- ✅ CSS 内联样式抽离为独立文件 + `common.css` 公共基础样式
- ✅ v1.5.2-beta2 生产打包完成，双实例 + 死实例清理端到端验证通过

### 进行中 / 待办
- ⏳ 构建时选择 ConPTY/WinPTY 后端（build-time-pty-backend-selection 方案已论证，未实施）：pywinpty 的 `PtyProcess.spawn(..., backend=Backend.WinPTY)` 可显式指定后端，同一份源码打 Win10/Win7 两个 exe
- ⏳ 生产打包建议关闭 `app.run(debug=True, use_reloader=True)`（frozen 环境下 reloader 会 spawn 多进程）

### 踩坑记录（打包相关）
- bilimusic 的 ffmpeg 路径：`FFMPEG_PATH = resourcePath('bin/ffmpeg.exe')` 在打包后解析为 `_MEIPASS/bin/ffmpeg.exe`。build 脚本 `--add-binary` 的目标目录必须与之一致：必须用 `bin\ffmpeg.exe;bin`（目标 `bin`），**不能**用 `bin\ffmpeg.exe;.`（目标根，会导致 ffmpeg 落在 `_MEIPASS/ffmpeg.exe`，代码找不到 → 回退系统 PATH → 学校电脑无 ffmpeg → 播放报 `[WinError 2] The system cannot find the file specified`）。两个 build 脚本（product/develop）均已改为 `;bin`。

---

## 五、历史重要改动记录

### v1.4.4（已合并 main）
- **B站音乐转码优化**：MP3 → WAV 转码，用完整版 ffmpeg（5.51MB，UPX 后 2.55MB），转码速度 3.4s → 0.1s
- 背景：v1.4.3 曾用 ffmpeg-mini（2.04MB）转 MP3，实测奇慢（约 3.4s），回退完整版 ffmpeg + WAV 方案
- 教训：轻量 ffmpeg-mini 转 MP3 性能差，WAV 转码快且音质无损

### v1.4.5-beta1
- 新增 `Installer/RunAsAdministrator.cmd`（sys32 安装：复制 exe 到 System32 + HKCU 注册表自启 + 关闭防火墙 + 80 端口规则 + 杀进程覆盖）

### v1.5.2（已合并 main，当前 beta2）
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
- `--collect-submodules functions` 必须保留（自动扫描依赖动态导入，PyInstaller 静态分析发现不了）
- `--add-data` 的源/目标路径必须与蓝图 root_path 匹配（`functions/xxx/templates` 等）
- `--collect-all winpty`（Cython 扩展用 hiddenimports 收集不到）
- `PYINSTALLER_CONFIG_DIR` 指向项目内 `.pyinstaller_cache`（规避沙箱拦截系统缓存目录）
- UPX 对个别 DLL 报 `NotCompressibleException` 是无害警告，可忽略
- 打包需在沙箱外执行

---

## 七、已知问题 / 注意事项

- **Windows 文件占用探测**（_MEI 清理实测结论，2026-08-29）：对运行实例已加载的 DLL（image section 映射），独占打开（`CreateFileW shareMode=0`）和目录重命名**均探测不到**；**只有删除（`os.remove`）会被拒绝**——判定文件是否被运行实例占用必须用删除探测
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
