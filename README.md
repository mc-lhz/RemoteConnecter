# RemoteConnecter — 学校电脑管理系统

Flask 后端 + 浏览器控制端的局域网远程管理工具：在一台机房电脑上运行单文件服务，任何浏览器打开即可远程操作它——无需在被控端安装客户端。

## 功能特性

- **多会话远程终端**：ConPTY 真终端（xterm.js），多会话 + 断线保活重连 + 刷新恢复画面回放
- **实时屏幕 + 远程键鼠**：MJPEG 推流带画质预设（流畅/标准/高清，页面隐藏自动暂停），远程点击/滚轮/拖拽/键盘（含 IME 与修饰键处理）
- **文件管理器**：网格视图 + 图片缩略图、拖拽/框选/长按批量操作、上传下载、压缩、预览、右键菜单（12 项）、排序与隐藏项
- **系统面板**：硬件状态（CPU/内存/磁盘/运行时长 + 走势曲线）、快动作（音量/锁屏/关显示器/睡眠）、电源管理、进程/窗口/应用管理
- **在线 Office 文档**：浏览器内编辑 docx/xlsx/pptx/pdf（OnlyOffice 系），见独立插件仓库 [RemoteOffice](https://github.com/mc-lhz/RemoteOffice)
- **VS Code 风格代码工作台**：Monaco 编辑、文件树、搜索/替换、快捷键、内嵌终端、F5 运行，见独立插件仓库 [RemoteVSCode](https://github.com/mc-lhz/RemoteVSCode)
- **插件系统**：`plugins/` 目录 + `plugin.json` 清单，四级目录覆盖（程序自带 / exe 同级 / ProgramData / APPDATA）
- 其它：B 站音乐播放/转码、屏幕截图控制、自动更新

## 快速开始

```bat
:: 开发运行（默认监听 0.0.0.0:80；RC_PORT 覆盖端口，RC_DEBUG=0 关闭调试器）
python39\python.exe RemoteConnecter.py

:: 生产打包（单文件 exe + UPX，产物 dist\RemoteConnecter.exe）
build.cmd
:: 调试打包（保留控制台窗口看日志）
build.cmd --show-console
```

浏览器打开 `http://<主机IP>/` 即进入首页；`/monitor` 系统面板、`/files` 文件管理器、`/terminal` 终端、`/screenshot` 实时屏幕、`/code` 代码工作台。

## 目录结构

```
RemoteConnecter/
├── RemoteConnecter.py    # 入口（装配宿主：内置蓝图 + 插件 + WebSocket）
├── hosts/                # 宿主层：blueprintHost（内置模块发现）/ pluginHost（插件加载）
├── functions/            # 内置业务模块（自动扫描 *_bp.py）
│   ├── main/             # 首页/文件浏览/上传
│   ├── term/             # 终端（多会话 ConPTY）
│   ├── screen/           # 实时屏幕 + 远程键鼠
│   ├── monitor/          # 系统面板
│   ├── files/            # 文件管理器
│   ├── bilimusic/        # B 站音乐
│   └── update/           # 自动更新
├── plugins/              # 插件目录（sample / proxy / process 入库；code、office 为独立仓库）
├── python39/             # 内嵌 Python 环境（不入库）
└── build.cmd             # 打包脚本（自动扫描模块与数据目录）
```

## 插件开发

新插件最小结构（放入 `plugins/<id>/`）：

```
plugins/<id>/
├── plugin.json       # {"id": "<id>", "entry": "<id>_bp.py"}
├── <id>_bp.py        # Blueprint，路由 /<id>/...
├── templates/        # 页面模板（可选）
└── static/           # 静态资源，自动挂载到 /<id>/static（可选）
```

插件在宿主中以 `rcplugin_<id>` 独立加载，单个插件失败不阻断启动；打包时 `build.cmd` 自动收集 `plugins/` 与内置模块，无需改脚本。

## 构建注意

- 必须用仓库内 `python39\python.exe`（嵌入式 3.9，干净依赖）
- **绝不能加 `-w`**（windowed 子系统会导致 ConPTY 崩溃 0xc0000142），生产用 `--hide-console hide-early`
- 新增业务零改脚本：`functions/<name>/<name>_bp.py` + 自动扫描（详见 `MEMORY.md` 打包章节）

## 长期维护文档

`MEMORY.md` 记录了历年关键改动、踩坑与打包/测试约定，是本项目的工程记忆主文档。