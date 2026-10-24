# 打包脚本自动扫描蓝图（纯 cmd）— 可行性分析与实施计划

## 一、结论

**纯 cmd 可行**。新建单一 `build.cmd`（生产行为），删除 `build-product.cmd`、`build-develop.cmd` 与残留 `RemoteConnecter.spec`。**不引入任何 Python 辅助脚本**。

自动扫描分两侧，都纯 cmd：
- **Python 模块侧**：`--collect-submodules functions` 单参数（已实测证明在嵌入 python39 下可用），不再逐个 `--hidden-import functions.*`。
- **数据文件侧**：`for /d` 循环遍历 `functions\*`，对存在的 `templates`/`static` 目录自动生成 `--add-data`。

新增业务只需建 `functions/<name>/<name>_bp.py`（含 templates/static 目录），`build.cmd` 零改动。

## 二、实测证据（Phase 1 探针）

### 证据 1：嵌入 python39 下 collect_submodules 可用（推翻 MEMORY.md 旧禁忌）
```
.\python39\python.exe -c "...collect_submodules('functions')"
→ ['functions','functions.bilimusic','functions.bilimusic.bilimusic',
   'functions.bilimusic.bilimusic_bp','functions.main','functions.main.file_bp',
   'functions.main.main_bp','functions.screen','functions.screen.screen_bp',
   'functions.shared','functions.term','functions.term.term_bp',
   'functions.update','functions.update.repoUpdate','functions.update.update_bp']
```
内嵌 python 直接 `import functions` 时 sys.path 无项目根（`_pth` 限制），但 PyInstaller 分析期会把主脚本所在目录（项目根）加入 sys.path，`collect_submodules` 即可枚举。**MEMORY.md「禁止 --collect-submodules，返回空」为历史误判**（build-develop.cmd 一直在用它且构建正常）。

### 证据 2：真实 PyInstaller 探针构建
`--collect-submodules functions` 构建成功，`PYZ-00.toc` 核实 `functions.main.main_bp`、`functions.main.file_bp`、`functions.term.term_bp`、`functions.screen.screen_bp`、`functions.update.update_bp`、`functions.bilimusic.bilimusic_bp` 全部入 PYZ。运行时 `pkgutil.iter_modules`（pyi_rth_pkgutil 钩子）扫 PYZ 发现蓝图，路径闭环成立。

### 证据 3：数据文件分布（for 循环的扫描对象，Phase 1 Glob 实测）
`functions/{bilimusic,main,screen,term,update}` 各含 templates+static；`functions/shared` 仅含 static。共 11 个数据目录——与现生产脚本 11 行 `--add-data` 完全一致。

## 三、现状问题
1. `build-product.cmd`：6 行 `--hidden-import functions.*` + 11 行 `--add-data` 全手写，新增业务漏改 → 打包后 404（历史事故根因）。
2. `build-product.cmd`（hidden-import）与 `build-develop.cmd`（collect-submodules）两套机制、两份维护。
3. 合并为单一 `build.cmd` 消除差异（调试留黑窗用 `--show-console` 开关）。

## 四、实施步骤

### 4.1 新建 `build.cmd`（唯一打包入口，纯 cmd）
```bat
@echo off
chcp 65001
cd /d %~dp0
setlocal enabledelayedexpansion
set "PYINSTALLER_CONFIG_DIR=%~dp0.pyinstaller_cache"

:: 默认生产(隐藏黑窗); 传 --show-console 则保留黑窗便于调试
set "consoleArgs= --hide-console hide-early"
if /i "%~1"=="--show-console" set "consoleArgs="

:: 自动扫描 functions\<pkg>\{templates,static} 生成 --add-data
set "dataArgs="
for /d %%p in (functions\*) do (
    set "pkg=%%~n"
    if exist "%%p\templates" set "dataArgs=!dataArgs! --add-data functions\!pkg!\templates;functions/!pkg!/templates"
    if exist "%%p\static"    set "dataArgs=!dataArgs! --add-data functions\!pkg!\static;functions/!pkg!/static"
)
set "dataArgs=!dataArgs! --add-data plugins;plugins"

echo 构建中...
.\python39\python.exe -m PyInstaller -F --noconfirm !consoleArgs! --upx-dir upx --collect-submodules functions --hidden-import hosts.blueprintHost --hidden-import hosts.pluginHost !dataArgs! --add-binary bin\ffmpeg.exe;bin --collect-all winpty RemoteConnecter.py
echo 构建完成: dist\RemoteConnecter.exe
```

要点：
- `for /d %%p in (functions\*)` 枚举业务包目录；`%%~n` 取目录名（`main`、`term`…）；`__pycache__` 无 templates/static，`if exist` 自然跳过。
- `--collect-submodules functions` 自动收全部 functions 模块（含 `__init__`、`bilimusic.py`、`repoUpdate.py` 等非 _bp 文件）——比现生产"逐 leaf hidden-import"多收不少收，无人 import 即不执行，无副作用（develop 脚本现状即如此）。
- `hosts.*` 在 functions 包外，单独 `--hidden-import`（保持现状）。
- `;` 在 cmd 中是普通字符（非分隔符），`--add-data src;dst` 无空格故为单一 token，安全。
- 固定尾部：`plugins;plugins`、`--add-binary bin\ffmpeg.exe;bin`、`--collect-all winpty` 不变。
- `cd /d %~dp0` 防 cwd 漂移（collect-submodules 依赖项目根在 sys.path）。

### 4.2 删除文件
- `build-product.cmd`、`build-develop.cmd`（内容被 `build.cmd` 覆盖；develop 唯一差异"留黑窗"由 `--show-console` 提供）。
- `RemoteConnecter.spec`（CLI 残留，不含真实参数，防 `PyInstaller xxx.spec` 误用）。

### 4.3 更新 MEMORY.md
- 「禁止 --collect-submodules functions」标记**历史误判**，改为"内嵌 python 直接 import 不可见 functions（_pth 无项目根），但 PyInstaller 分析期项目根在 sys.path，collect_submodules 可用（探针 PYZ 已验证）"。
- 打包指南：入口统一 `build.cmd`；"新增业务建 `functions/<name>/<name>_bp.py`（含 templates/static），打包零改动"；`--show-console` 说明；删除双脚本描述。

## 五、假设与决策
1. 单一生产行为：默认 `--hide-console hide-early`（已全量验证）；调试用 `--show-console`。
2. 保留 `python39\` 内嵌 Python 作打包解释器。
3. `plugins/` 官方插件 `--add-data plugins;plugins` 不变，写死 dataArgs 尾部。
4. UPX、`PYINSTALLER_CONFIG_DIR`、ffmpeg 落 `bin` 目标策略不变。
5. 模块收集用 `collect-submodules`（非逐 leaf hidden-import 循环）——更抗脆弱、已实测。

## 六、验证步骤
1. **参数等价性（dry-run）**：临时把最后一行 PyInstaller 调用换成 `echo`，跑 `build.cmd` 打印最终参数，与旧 `build-product.cmd` 对照：collect-submodules 覆盖 6 个 _bp、11 项 add-data、plugins、ffmpeg、winpty、hide-console 齐全（在删旧脚本前执行便于 diff）。
2. **生产打包**：跑 `build.cmd`，`dist\RemoteConnecter.exe` 生成成功，大小接近 v1.6 基线（~20.1MB）。
3. **全量冒烟**：启动 exe（reloader 3 进程预期），`/`、`/terminal`、`/screenshot`、`/download`、`/update`、`/bilimusic`、`/shared/static/common.css`、`/sample`、`/sample/static/sample.js`、`/proxy` 全 200；测完杀进程、端口 80 释放。
4. **自动扫描增量证明（核心验收）**：临时新建 `functions/demo/`（`__init__.py` + `demo_bp.py` 含 `/demo` 路由 + `templates/demo.html`）→ 重打包 → `PYZ-00.toc` 含 `functions.demo.demo_bp`、数据含 `functions/demo/templates`、`/demo` 200 → **还原 demo 目录**再打包恢复基线。
5. **清理**：`Remove-Item .build_tmp -Recurse`（Phase 1 探针残留）、确认无残留临时物、杀所有 RemoteConnecter 进程。

## 七、风险
| 风险 | 评估 | 缓解 |
|---|---|---|
| cmd `for` 嵌套 + 延迟展开书写错误 | 中（纯 cmd 主要风险点） | 验证步骤 1 先 dry-run 打印参数核对 |
| `collect-submodules` 收进 `repoUpdate.py`（bug 草稿） | 低：无人 import 不执行；develop 现状即如此 | 不处理 |
| `;` 在 dataArgs 中被误当分隔 | 低：cmd 不认 `;` 为分隔符，token 无空格 | dry-run 核对 |
| 旧 spec 误用 | 低 | 删除 RemoteConnecter.spec |
| cwd 漂移 | 中 | `cd /d %~dp0` |
