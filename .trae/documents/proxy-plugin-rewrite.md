# 计划：用 GithubMirror 思路重写 RemoteConnecter 的 proxy 插件

## 1. 摘要（Summary）

把 GithubMirror（Cloudflare Worker 反向代理）的**"三层资源改写"思路**移植到 RemoteConnecter 本地 `plugins/proxy` 插件：

- 保留现有 URL 形式：`http://localhost/proxy/direct/<完整上游URL>`（用户确认沿用）
- 新增 **HTML 改写层**：把代理页面 HTML 里的绝对 URL 全部改写为经 `/proxy/direct/` 走本地代理
- 新增 **首屏内联脚本层**：注入 `<head>`，改写页面 `fetch` / XHR 的 URL（补 SW 激活前空窗）
- HTML 解析改用 **BeautifulSoup4**，通过**插件私有 `lib/` 目录**提供（新增 `pluginHost` 的 lib 机制，不污染主程序依赖、不进 exe）

目标：代理 GitHub 等站点时，页面内所有资源请求都改走本地 `/proxy/direct/…`，绕开本地 hosts `127.0.0.1` 映射导致的 **Chrome Private Network Access（loopback）拦截**。

**本次不做（Out of Scope）**：Service Worker 层（HttpOnly 环境/局域网 IP 下 SW 作用域与证书问题多，GithubMirror 的 SW 依赖公网 HTTPS 域名，本地不合适）。若后续需要，另开计划。

**工作流约束**：不新建分支，直接在 `main` 上改动，与既有开发方式一致。

## 2. 现状分析（Current State Analysis）

### 2.1 proxy 插件现状
[proxy_bp.py](file:///d:/desktop/py/NewProject/RemoteConnecter/plugins/proxy/proxy_bp.py) 仅 42 行：
- 3 条路由：`/proxy`（内联 HTML 双链接）、`/proxy/direct/<path:url>`（GET/POST 转发）、`/proxy/proxy/cf`（硬编码 echo，路径写重复）
- `direct` 缺陷：非 GET/POST 报 `UnboundLocalError`；无 `timeout`（worker 可挂死）；无 `requests` 异常捕获；一律返回 `response.text` 丢状态码/头/二进制；调试 `print` 残留
- 未对齐 sample 的规范：硬编码 `proxy_bp` / `/proxy`，未从 `plugin.json` 读 `id` 锚定

### 2.2 插件宿主机制
[pluginHost.py](file:///d:/desktop/py/NewProject/RemoteConnecter/hosts/pluginHost.py)：
- 四级目录：`_MEI/plugins`（自带）→ exe 同级 → PROGRAMDATA → APPDATA，同 id 后者覆盖
- `plugin.json` 字段：`id`（必需）、`entry`（必需）、`lib`（可选，默认 `'lib'`，第 92 行）
- **lib 机制已存在**：第 102-104 行 `if libPath and libPath not in sys.path: sys.path.insert(0, libPath)` —— 插件私有依赖目录已支持，加载后不弹出（支持延迟 import）
- 用 `importlib.util.spec_from_file_location('rcplugin_'+id, filepath)` 显式路径加载，绕过 `_pth` 限制

### 2.3 打包机制
[build.cmd](file:///d:/desktop/py/NewProject/RemoteConnecter/build.cmd) 第 44 行 `--add-data "plugins;plugins"` —— `plugins/` 整目录（含子目录）进 `_MEI` 自带层。
**关键推论**：只要把 bs4 放进 `plugins/proxy/lib/`，就会被 `--add-data plugins;plugins` 一并打包，**build.cmd 无需改动**。

### 2.4 蓝图注册约定
[blueprintHost.py](file:///d:/desktop/py/NewProject/RemoteConnecter/hosts/blueprintHost.py) 第 15-17 行：变量名以 `_bp` 结尾且是 `Blueprint` 实例即注册。

### 2.5 可复用参考
`%TEMP%\GithubMirror\src\index.js`（已 clone）中的核心逻辑：
- 属性改写清单：`a/area/link[href]`、`script/img/iframe/embed/source/video/audio[src]`、`img/source[srcset]`、`form[action]`、`link[data-href|data-base-href]`、`img[data-src]`、`meta[content]`
- 运行时改写：patch `window.fetch`（含 `Request` 对象）+ `XMLHttpRequest.prototype.open`
- 防二次改写：`hostname` / URL 已含 `/proxy/direct/` 前缀则跳过וי

## 3. 方案设计（Proposed Changes）

### 3.1 文件结构（改造后）
```
plugins/proxy/
├── plugin.json          # 加 "lib": "lib"
├── proxy_bp.py          # 重写：路由 + 转发 + HTML 改写调用
├── lib/
│   └── bs4/             # BeautifulSoup4 + 依赖（soupsieve），纯 .py 放这里
└── static/
    └── proxy_inject.js  # 首屏脚本（或内联进 HTML，二选一，见 3.5）
```
> `bs4` 纯 Python 包，无 `.pyd`，放入 `lib/` 即可；`soupsieve` 是 bs4 唯一运行时依赖，一并放入。

### 3.2 [plugin.json](file:///d:/desktop/py/NewProject/RemoteConnecter/plugins/proxy/plugin.json)
```json
{
    "id": "proxy",
    "entry": "proxy_bp.py",
    "lib": "lib"
}
```
> **Why**：显式声明私有依赖目录，`pluginHost` 会把它 `sys.path.insert(0, ...)`。
> **How**：新增一行 `"lib": "lib"`。

### 3.3 `plugins/proxy/lib/` 内容
- 从 `python39\Lib\site-packages`（或 pip 安装到临时目录）取 `bs4/` 与 `soupsieve/` 两个纯 Python 包，复制进 `plugins/proxy/lib/`
- 需确认 bs4 无 C 扩展（`bs4`/`soupsieve` 均为纯 py，✅ 无需 .pyd）
- **不修改** `build.cmd`（`--add-data plugins;plugins` 已覆盖）

### 3.4 [proxy_bp.py](file:///d:/desktop/py/NewProject/RemoteConnecter/plugins/proxy/proxy_bp.py) 重写
**保留**：
- 从 `plugin.json` 读 `id` 并锚定（对齐 sample 规范），蓝图名 `f'{pluginID}_bp'`
- 路由 `/proxy`（首页）、`/proxy/direct/<path:url>`（GET/POST 转发）
- `HOP_BY_HOP_HEADERS` 逐跳头过滤

**修复 `direct`**：
1. 支持**任意 method**（GET/POST/PUT/DELETE…非 GET 透传 `data=request.get_data()`）
2. **加 `timeout`**（如 20s），防 worker 挂死
3. **捕获** `requests.exceptions.RequestException` → 返回 502 JSON
4. **完整透传**：`Response(response.content, status=response.status_code, headers=过滤后的响应头)`，保留二进制/图片/状态码；删 `Content-Encoding`（requests 已解压）、`Content-Length`（若改写 HTML 则变长）
5. 删除 `print` 调试，改 `Log.i`
6. URL 合法性：仅允许 `http`/`https` scheme，其余 400

**新增 HTML 改写**：
- 判定 `Content-Type` 含 `text/html` 且状态 2xx/3xx：
  - 用 bs4 解析 → 遍历 3.5 的属性清单 → 把绝对 `http(s)://host/path` 改写为 `/proxy/direct/http(s)://host/path`
  - 相对 URL 不动（其 host 本来就是代理 host，天然经代理）；已是 `/proxy/direct/` 前缀的跳过（防二次）
  - 注入首屏脚本到 `<head>`
  - 重新序列化（`str(soup)`，强制 `decode_contents`/指定 `formatter` 保留原样）+ 更新 `Content-Length`
- 非 HTML：原样字节透传

### 3.5 首屏内联脚本（改写 fetch/XHR）
在改写后的 HTML `<head>` 注入：
```js
(function(){
  var PREFIX = '/proxy/direct/';
  function rewrite(url){
    if (typeof url !== 'string') return url;
    if (url.indexOf(PREFIX) === 0) return url;              // 防二次
    if (!/^https?:\/\//i.test(url)) return url;             // 仅绝对 http(s)
    return location.origin + PREFIX + url;
  }
  // patch window.fetch（支持字符串与 Request 对象两种入参）
  var nativeFetch = window.fetch;
  if (nativeFetch) {
    window.fetch = function(input, init){
      if (input instanceof Request) {
        var newUrl = rewrite(input.url);
        if (newUrl !== input.url) input = new Request(newUrl, input);
      } else {
        input = rewrite(input);
      }
      return nativeFetch.call(this, input, init);
    };
  }
  // patch XMLHttpRequest.prototype.open 同理（字符串 url 参数改写）
  var nativeOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url, asyncFlag, user, password){
    return nativeOpen.call(this, method, rewrite(url), asyncFlag, user, password);
  };
})();
```
> **放置**：推荐**内联进 HTML 字符串常量**（与 GithubMirror 一致，避免额外静态文件请求与打包遗漏）；若偏好独立文件则放 `plugins/proxy/static/proxy_inject.js`，需确认 `static_url_path` 与 Flask 蓝图静态路由可达。
> **决策**：采用**内联字符串常量**（简单、无额外请求、打包天然覆盖）。

### 3.6 命名规范（用户强约束）
- 所有变量/函数/属性：**小驼峰**（`pluginID`、`upstreamUrl`、`rewriteHtmlUrls`、`hopByHopHeaders`）
- 常量：**全大写下划线**（`HOP_BY_HOP_HEADERS`、`URL_ATTR_MAP`）
- 类名：PascalCase（本次无自定义类）

## 4. 假设与决策（Assumptions & Decisions）

| 项 | 决策 | 依据 |
|---|---|---|
| URL 形式 | `/proxy/direct/<完整上游URL>` | 用户明确指定沿用 |
| HTML 解析 | **BeautifulSoup4**，放插件 `lib/` | 用户明确指定 |
| 打包 | 不改 `build.cmd` | `--add-data plugins;pluginsemen` 已覆盖 lib/ |
| Service Worker | **不做** | 本地 IP/HttpOnly 不适合，超出本次范围 |
| 首屏脚本 | 内联 HTML 字符串 | 简单、无额外请求 |
| lib 加载 | 复用现有 `pluginHost` lib 机制 | 已存在，无需改宿主 |
| 解析器 | bs4 用内置 `html.parser`（不引 lxml） | 避免二进制依赖，体积更小 |

## 5. 验证步骤（Verification）

1. **依赖就位**：`plugins/proxy/lib/` 下放入 `bs4/`、`soupsieve/`；`python39\python.exe -c "import sys; sys.path.insert(0,'plugins/proxy/lib'); import bs4; print(bs4.__version__)"` 通过
2. **开发态冒烟**：启动 `python39\python.exe RemoteConnecter.py`，访问：
   - `http://127.0.0.1/proxy` → 200，首页
   - `http://127.0.0.1/proxy/direct/https://cn.bing.com` → 200，且返回 HTML 内的 `href`/`src` 已被改写为 `/proxy/direct/https://…`
   - `http://127.0.0.1/proxy/direct/https://api.github.com/`（JSON）→ 200 原样透传，未改写
   - 非法 scheme：`/proxy/direct/file:///etc/passwd` → 400
3. **fetch 改写验证**：代理页含内联 `<script>`，`window.fetch` 已被 patch（检查源码字符串）
4. **打包验证**：`build.cmd` 打包 → 确认 exe 体积变化合理（多了 bs4）→ dist 不放同级 plugins → 启动 exe → 重复步骤 2 路由全过（确认 lib 从 `_MEI/plugins/proxy/lib` 加载）
5. **离线验证**：断网/无外网时，`/proxy` 首页仍 200（证明 lib 已随插件加载，非运行时下载）
6. **回归**：`/sample`、`/sample/static/sample.js` 等既有插件路由不受影响
7. **清理**：杀进程、释放 80 端口

## 6. 待办清单（Tasks）

1. 从 python39 环境导出 bs4 + soupsieve 到 `plugins/proxy/lib/`
2. 更新 `plugin.json` 加 `lib` 字段
3. 重写 `proxy_bp.py`（路由规范 + direct 修复 + HTML 改写 + 注入）
4. 开发态冒烟测试
5. 打包 + 打包态冒烟测试
6. 更新 MEMORY.md（proxy 插件新能力 + lib 依赖机制说明）
7. 杀进程清理