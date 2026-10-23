# 终端页：单击状态（未连接）显示/隐藏控制键区

## 摘要

终端页顶部工具栏的状态指示 `#status`（初始文本"未连接"）目前不可交互。本计划让**单击该状态文字**切换底部 `#control-keys` 控制键区（Ctrl+C、方向键、Tab、ESC）的显示/隐藏，用于窄屏或不需要控制键时腾出终端高度。

## 现状分析

- [term.html](file:///d:/desktop/py/NewProject/RemoteConnecter/functions/term/templates/term.html)：
  - `#bar` 工具栏内含 `#status`（L24，初始文本"未连接"，由 `setStatus()` 更新文本与 `ok`/`err` class）
  - `#control-keys`（L29-55）为 6 个 `.control-key` 按钮的 flex 容器
- [term.css](file:///d:/desktop/py/NewProject/RemoteConnecter/functions/term/static/term.css)：
  - `#status`（L44-53）已有 `white-space: nowrap; overflow: hidden; text-overflow: ellipsis`，无交互样式
  - `#control-keys`（L79-86）flex-wrap 容器，`margin-top: 4px`
- [term.js](file:///d:/desktop/py/NewProject/RemoteConnecter/functions/term/static/term.js)：
  - `setStatus(text, cls)`（L24-27）每次连接/断开都会重写 `statusEl.className`——**隐藏状态的 class 不能挂在 `#status` 上，否则会被 setStatus 清掉**；应把隐藏标记挂在 `#control-keys` 元素自身（`statusEl.className = cls || ''` 只影响 status 自己，互不干扰）
- 连接后 `#status` 文本变为"已连接: xxx"，单击行为依然生效（切换的是控制键区，与连接状态无关）

## 改动方案（3 个文件，均为最小改动）

### 1. `functions/term/static/term.js`
在 `setStatus` 定义之后新增：

```js
// 单击状态文字 → 切换控制键区显示/隐藏（标记挂在 #control-keys 上，避免被 setStatus 重写 className 清掉）
const controlKeys = document.getElementById('control-keys');
const KEYS_PREF_KEY = 'showControlKeys';
if (localStorage.getItem(KEYS_PREF_KEY) === '0') {
    controlKeys.classList.add('hidden');
}
statusEl.addEventListener('click', function () {
    controlKeys.classList.toggle('hidden');
    localStorage.setItem(KEYS_PREF_KEY, controlKeys.classList.contains('hidden') ? '0' : '1');
});
```

要点：
- 隐藏标记 class（`hidden`）挂在 `#control-keys` 自身，与 `setStatus` 对 `#status` 的 className 重写互不干扰
- 用 `localStorage`（键 `showControlKeys`）记住用户选择，刷新后保持
- 切换时**不调用** `fit.fit()`/`sendResize()`（按用户要求先不加）

### 2. `functions/term/static/term.css`
在 `#status` 规则附近新增两条：

```css
#status { cursor: pointer; user-select: none; }   /* 并入现有 #status 块 */
#control-keys.hidden { display: none; }
```

- `cursor: pointer` 提示可点（不改变视觉风格，符合现有深色 GitHub 风）
- `display: none` 让终端区 `#terminal`（`flex: 1`）自动占满腾出的高度

### 3. `functions/term/templates/term.html`
`#status` 行加 `title` 提示，不改结构：

```html
<span id="status" title="单击 显示/隐藏控制键">未连接</span>
```

## 假设与决策

- **交互入口选 `#status` 而非 `#control-keys` 本身**：用户明确要求"单击未连接（状态文字）"。已连接时文本变为"已连接: cmd"，仍可点击，行为一致
- **隐藏用 `display: none`** 而非 `visibility: hidden`，使终端区真正变高
- **加 localStorage 记忆**：刷新/重开页面保持用户选择，属该功能自然预期；键名遵循小驼峰
- 不做：不加额外按钮/图标、不动控制键按钮本身、不动后端

## 验证步骤

1. 本地 `python RemoteConnecter.py`（开发态）打开 `http://localhost/terminal`
2. 单击"未连接"→ 控制键区消失、终端区变高、状态文字保持原样
3. 再单击 → 恢复显示
4. 刷新页面 → 保持上次的显示/隐藏状态（`localStorage['showControlKeys']`）
5. 点 cmd 预设连接后单击状态文字 → 仍能切换；断开后依旧
6. 窄屏（<640px）下同样可切换
