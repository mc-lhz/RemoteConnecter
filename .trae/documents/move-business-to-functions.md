# 计划：新建 functions/ 目录收纳业务模块

## Summary
在项目根目录新建 `functions/` 文件夹，将 5 个业务蓝图目录（`main`、`screen`、`term`、`bilimusic`、`update`）及公共静态资源目录 `shared` 移入其中。主入口 `RemoteConnecter.py`、工具 `utils.py`、日志 `Logcat.py`、构建脚本和二进制 `bin/` 留在根目录。

## Current State Analysis
当前目录结构：
```
RemoteConnecter/
├── RemoteConnecter.py   # 主入口（Flask app，注册全部蓝图）
├── utils.py             # 工具库（resourcePath 基于 __file__ = 根目录）
├── Logcat.py            # 日志模块
├── build-product.cmd    # 生产打包脚本
├── build-develop.cmd    # 开发打包脚本
├── main/  screen/  term/  bilimusic/  update/   # 5 个业务蓝图
├── shared/static/       # 公共静态资源（jquery 等）
├── bin/ffmpeg.exe       # 二进制（用户选择不移动）
├── upx/  Installer/  python39/  ...
```

依赖关系（已确认）：
1. **蓝图 import**：`RemoteConnecter.py` 用 `from main.main_bp import main_bp` 等绝对导入；蓝图内部用 `from utils import *`、`import Logcat` 绝对导入顶层模块。运行时入口在根目录 → `sys.path` 含根目录 → 移动后这些导入依然有效。
2. **相对导入**：`bilimusic/bilimusic_bp.py` 用 `from . import bilimusic`（包内相对导入，移动后有效）。
3. **template/static**：蓝图声明 `template_folder='templates'`、`static_folder='static'`，Flask 相对蓝图 root_path（即蓝图文件所在目录）解析 → 移动后自动指向 `functions/main/templates` 等。
4. **shared 静态路由**：`RemoteConnecter.py` 的 `sharedStatic` 用 `resourcePath('shared/static')` → 需改为 `resourcePath('functions/shared/static')`。
5. **bin 路径**：`bilimusic_bp.py` 用 `resourcePath('bin/ffmpeg.exe')`，`bin/` 不移动 → 不变。
6. **构建脚本**：`--add-data` 源路径加 `functions\` 前缀，且**目标路径必须同步改为 `functions/main/templates` 等**（否则打包后蓝图 root_path 在 `_MEIPASS/functions/main`，与资源目录不匹配 → 页面 404）。
7. **namespace package**：Python 3 支持无 `__init__.py` 的目录作为命名空间包（当前 `main/` 等即如此），`from functions.main.main_bp import ...` 可直接工作；建议在 `functions/` 加一个空 `__init__.py` 显式声明为包。

## Proposed Changes

### 1. 创建 `functions/__init__.py`（空文件）
明确将 `functions` 声明为 Python 包。

### 2. 移动目录（git mv 保留历史）
```
git mv main functions/main
git mv screen functions/screen
git mv term functions/term
git mv bilimusic functions/bilimusic
git mv update functions/update
git mv shared functions/shared
```
移动后 `functions/` 下各业务目录保持不变（各含 `templates/`、`static/`、蓝图文件）。

### 3. 修改 `RemoteConnecter.py`（根目录入口）
- 5 行蓝图导入：
  - `from main.main_bp import main_bp` → `from functions.main.main_bp import main_bp`
  - `from main.file_bp import file_bp` → `from functions.main.file_bp import file_bp`
  - `from screen.screen_bp import screen_bp` → `from functions.screen.screen_bp import screen_bp`
  - `from bilimusic.bilimusic_bp import bilimusic_bp` → `from functions.bilimusic.bilimusic_bp import bilimusic_bp`
  - `from update.update_bp import update_bp` → `from functions.update.update_bp import update_bp`
  - `from term.term_bp import term_bp, sock` → `from functions.term.term_bp import term_bp, sock`
- `sharedStatic` 路由：`resourcePath('shared/static')` → `resourcePath('functions/shared/static')`

### 4. 修改 `build-product.cmd`（根目录）
`--add-data` 全部加 `functions\` 前缀（源+目标同步）：
- `"functions\main\templates;functions/main/templates"`
- `"functions\main\static;functions/main/static"`
- `"functions\screen\templates;functions/screen/templates"`
- `"functions\screen\static;functions/screen/static"`
- `"functions\term\templates;functions/term/templates"`
- `"functions\term\static;functions/term/static"`
- `"functions\bilimusic\templates;functions/bilimusic/templates"`
- `"functions\bilimusic\static;functions/bilimusic/static"`
- `"functions\update\templates;functions/update/templates"`
- `"functions\update\static;functions/update/static"`
- `"functions\shared\static;functions/shared/static"`
- `--add-binary "bin\ffmpeg.exe;."` 不变（bin 不移动）
- 入口 `RemoteConnecter.py` 不变

### 5. 修改 `build-develop.cmd`（根目录）
与 build-product.cmd 相同的路径前缀调整。

### 6. 蓝图内部代码
**无需修改**：
- `from utils import *` / `import Logcat`：绝对导入，运行时入口在根目录，sys.path 含根目录，保持有效
- `from . import bilimusic`：包内相对导入，有效
- template_folder/static_folder：相对蓝图自身，自动指向新位置
- 所有 HTML/JS 的 URL（`/main/static/...`、`/screen/screenshot` 等）：这些是 HTTP 路由/蓝图 url_prefix，与磁盘目录无关，**不变**

## Assumptions & Decisions
- 新文件夹名 `functions`（用户确认）
- 移动范围：main/screen/term/bilimusic/update + shared（用户确认）；**不移动** bin（用户未选）
- utils.py、Logcat.py 留在根目录（用户未选移动）—— 绝对导入保持有效
- RemoteConnecter.py 留在根目录（用户确认），作为 PyInstaller 入口
- `functions/` 加空 `__init__.py` 显式声明包（虽 namespace package 也可行，但更明确）

## Verification
1. **导入验证**：`python -c "import RemoteConnecter"` 或启动 Flask，确认 6 个蓝图全部注册成功、无 ModuleNotFoundError
2. **路由验证**：启动服务后访问以下路径均返回 200：
   - `/`（重定向 /main/）、`/main/`
   - `/screen/screenshot`、`/term/terminal`、`/bilimusic`、`/update`
   - 静态：`/shared/static/jquery.js`、`/main/static/index.js`、`/screen/static/screen-control.js`、`/term/static/images/cmd.png`
3. **API 验证**：`POST /main/api/command`、`GET /bilimusic/api/bilimusic/status` 正常
4. **git 状态**：确认移动后为 rename（R）记录，无内容意外变更
