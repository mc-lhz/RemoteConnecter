// 缓存首帧的屏幕分辨率（MJPEG naturalWidth 在流更新时可能不可靠；
// 画质预设可能按 scale 缩放画面，点击映射必须用真实屏幕分辨率）
var screenW = 0, screenH = 0;

// 优先从服务端获取真实分辨率（缩放后 naturalWidth 只是缩放后尺寸）
fetch('/screenshot/api/size')
    .then(function (res) { return res.json(); })
    .then(function (data) {
        if (data && data.width > 0 && data.height > 0 && !screenW) {
            screenW = data.width;
            screenH = data.height;
            console.log('屏幕分辨率(服务端): ' + screenW + 'x' + screenH);
        }
    })
    .catch(function () { /* 拉取失败回退 naturalWidth */ });

// 定期检查并缓存分辨率（回退路径）
function checkResolution() {
    if (streamImg.naturalWidth > 0 && !screenW) {
        screenW = streamImg.naturalWidth;
        screenH = streamImg.naturalHeight;
        console.log('屏幕分辨率(流回退): ' + screenW + 'x' + screenH);
    }
}
setInterval(checkResolution, 500);

/**
 * 将元素内点击坐标映射到实际屏幕坐标
 * 正确处理 object-fit: contain 造成的黑边偏移
 */
function imgToScreen(img, clientX, clientY) {
    // 如果还没获取到分辨率，尝试立即获取
    if (!screenW || !screenH) {
        if (img.naturalWidth > 0) {
            screenW = img.naturalWidth;
            screenH = img.naturalHeight;
            console.log('屏幕分辨率 (实时获取): ' + screenW + 'x' + screenH);
        } else {
            console.warn('分辨率未就绪');
            return null;
        }
    }

    var rect = img.getBoundingClientRect();
    var clickX = clientX - rect.left;
    var clickY = clientY - rect.top;

    // 使用缓存的屏幕分辨率
    var imgAspect = screenW / screenH;
    var containerAspect = rect.width / rect.height;
    var renderW, renderH, offsetX, offsetY;

    if (imgAspect > containerAspect) {
        // 图片比容器更宽（横向），上下有黑边
        renderW = rect.width;
        renderH = rect.width / imgAspect;
        offsetX = 0;
        offsetY = (rect.height - renderH) / 2;
    } else {
        // 图片比容器更高（纵向），左右有黑边
        renderH = rect.height;
        renderW = rect.height * imgAspect;
        offsetX = (rect.width - renderW) / 2;
        offsetY = 0;
    }

    // 检查点击是否在图片区域内（而非黑边区域）
    if (clickX < offsetX || clickX > offsetX + renderW ||
        clickY < offsetY || clickY > offsetY + renderH) {
        console.log('点击在黑边区域，忽略');
        return null;
    }

    var screenX = Math.round((clickX - offsetX) / renderW * screenW);
    var screenY = Math.round((clickY - offsetY) / renderH * screenH);

    // 边界检查
    screenX = Math.max(0, Math.min(screenW - 1, screenX));
    screenY = Math.max(0, Math.min(screenH - 1, screenY));

    return { x: screenX, y: screenY };
}

function sendControl(params) {
    var url = '/screenshot/api/control?' + params;
    $.get(url)
        .done(function(response) { console.log('控制响应:', response, params); })
        .fail(function(xhr, status) { console.error('控制请求失败:', status, params); });
}

function sendClick(x, y, button, count) {
    button = button || 'left';
    sendControl('controlType=mouse&x=' + x + '&y=' + y
        + '&button=' + button + '&count=' + (count || 1));
}

function sendMove(x, y) {
    sendControl('controlType=move&x=' + x + '&y=' + y);
}

function sendPress(button) {
    sendControl('controlType=press&button=' + (button || 'left'));
}

function sendRelease(button) {
    sendControl('controlType=release&button=' + (button || 'left'));
}

// ---- 左键点击 / 拖拽 ----
// 简单点击沿用 click 事件；按住并移动超过阈值进入拖拽模式
// （远端 press → move... → release），拖拽结束后的 click 事件被抑制
var dragArmed = false;
var dragging = false;
var dragStart = null;      // {clientX, clientY, screenX, screenY}
var lastMoveSend = 0;
var suppressClick = false;

streamImg.addEventListener('mousedown', function(e) {
    if (e.button !== 0) { return; }
    var p = imgToScreen(this, e.clientX, e.clientY);
    if (!p) { return; }
    dragArmed = true;
    dragging = false;
    dragStart = { clientX: e.clientX, clientY: e.clientY, screenX: p.x, screenY: p.y };
    e.preventDefault();
});

streamImg.addEventListener('mousemove', function(e) {
    if (!dragArmed || !(e.buttons & 1)) { return; }
    if (!dragging) {
        var dx = e.clientX - dragStart.clientX;
        var dy = e.clientY - dragStart.clientY;
        if (dx * dx + dy * dy < 36) { return; }   // 6px 阈值
        dragging = true;
        sendMove(dragStart.screenX, dragStart.screenY);
        sendPress('left');
        lastMoveSend = Date.now();
    }
    var now = Date.now();
    if (now - lastMoveSend < 60) { return; }
    lastMoveSend = now;
    var p = imgToScreen(this, e.clientX, e.clientY);
    if (p) { sendMove(p.x, p.y); }
});

function endDrag() {
    dragArmed = false;
    if (dragging) {
        dragging = false;
        sendRelease('left');
        suppressClick = true;
        setTimeout(function () { suppressClick = false; }, 300);
    }
}

document.addEventListener('mouseup', endDrag);
window.addEventListener('blur', endDrag);

streamImg.addEventListener('click', function(e) {
    if (suppressClick) { return; }
    var pos = imgToScreen(this, e.clientX, e.clientY);
    if (!pos) { console.warn('分辨率未就绪'); return; }
    sendClick(pos.x, pos.y);
});

// ---- 滚轮 ----
// Chromium deltaY>0 为向下；pynput 垂直正值向上，故取反。
// 60ms 内的多次滚动累积合并，避免请求洪泛
var wheelTimer = null;
var wheelDX = 0;
var wheelDY = 0;

streamImg.addEventListener('wheel', function(e) {
    e.preventDefault();
    var step = 1;
    if (e.deltaMode === 1) { step = 3; }
    else if (e.deltaMode === 2) { step = 16; }
    if (e.deltaX) { wheelDX += Math.sign(e.deltaX) * step; }
    if (e.deltaY) { wheelDY += -Math.sign(e.deltaY) * step; }
    if (wheelTimer) { return; }
    wheelTimer = setTimeout(function() {
        wheelTimer = null;
        var sendX = Math.max(-10, Math.min(10, wheelDX));
        var sendY = Math.max(-10, Math.min(10, wheelDY));
        wheelDX = 0;
        wheelDY = 0;
        if (sendX || sendY) {
            sendControl('controlType=wheel&dx=' + sendX + '&dy=' + sendY);
        }
    }, 60);
}, { passive: false });

// 禁用右键菜单 → 发送右键
streamImg.addEventListener('contextmenu', function(e) {
    e.preventDefault();
    var pos = imgToScreen(this, e.clientX, e.clientY);
    if (!pos) return;
    sendClick(pos.x, pos.y, 'right');
});

// ============================================================
//  键盘输入
// ============================================================

// 当前按下的修饰键集合
var heldModifiers = new Set();
// 当前修饰键链是否已产生过输出（普通键已随组合发送，或纯修饰组合已成型发送）
var modifierComboSent = false;

// 前端 KeyboardEvent.key → 后端修饰键名
var MODIFIER_MAP = {
    'Control': 'ctrl',    'Alt': 'alt',
    'Shift': 'shift',     'Meta': 'cmd',
    'AltGraph': 'alt_gr',
};

// 逐键多参数传输（keys=a&keys=b），可表达任意字符（包括 '+'）
function sendKeys(keyList) {
    var url = '/screenshot/api/control?controlType=keyboard';
    keyList.forEach(function(k) { url += '&keys=' + encodeURIComponent(k); });
    console.log('发送按键:', keyList.join('+'));

    $.get(url)
        .done(function(response) {
            console.log('键盘响应:', response);
        })
        .fail(function(xhr, status, error) {
            console.error('键盘请求失败:', status, error);
        });
}

function currentModifierList() {
    // 固定顺序输出，符合真实按键习惯
    var order = ['ctrl', 'alt', 'shift', 'cmd', 'alt_gr'];
    return order.filter(function(m) { return heldModifiers.has(m); });
}

// 把 JS 的 KeyboardEvent 映射成后端能识别的键名；返回 null 表示应忽略
function keyToName(e) {
    if (MODIFIER_MAP[e.key]) return MODIFIER_MAP[e.key];

    // 输入法接管（中文输入法组字阶段），无法透传
    if (e.key === 'Process' || e.key === 'Unidentified') {
        console.warn('按键被输入法接管已忽略；如需输入英文请先切换输入法');
        return null;
    }
    // 死键（重音组合引导键），忽略
    if (e.key === 'Dead') { return null; }

    // 单字符：字母/数字/符号
    if (e.key.length === 1) return e.key;

    // 特殊键：统一小写并对齐名称
    var k = e.key.toLowerCase();
    if (k === 'escape') return 'esc';
    if (k === ' ') return 'space';
    if (k === 'capslock') return 'caps_lock';
    if (k === 'numlock') return 'num_lock';
    if (k === 'scrolllock') return 'scroll_lock';
    if (k === 'pageup') return 'page_up';
    if (k === 'pagedown') return 'page_down';
    if (k === 'printscreen') return 'print_screen';
    if (k === 'contextmenu') return 'menu';
    if (k.indexOf('arrow') === 0) return k.slice(5);  // ArrowLeft → left
    return k;
}

document.addEventListener('keydown', function(e) {
    // 修饰键：只记录状态；组合在普通键到达或纯修饰组合成型时发送
    if (MODIFIER_MAP[e.key]) {
        if (heldModifiers.size === 0) { modifierComboSent = false; }
        heldModifiers.add(MODIFIER_MAP[e.key]);
        // 纯修饰组合（如 Ctrl+Shift 切输入法）在第二个修饰键按下瞬间成型
        if (heldModifiers.size >= 2 && !modifierComboSent) {
            sendKeys(currentModifierList());
            modifierComboSent = true;
        }
        e.preventDefault();
        return;
    }

    var keyName = keyToName(e);
    if (keyName === null) { e.preventDefault(); return; }

    sendKeys(currentModifierList().concat([keyName]));
    modifierComboSent = true;

    // 阻止浏览器默认快捷键
    e.preventDefault();
});

document.addEventListener('keyup', function(e) {
    if (!MODIFIER_MAP[e.key]) { return; }
    heldModifiers.delete(MODIFIER_MAP[e.key]);
    // 孤立修饰键：按下后直接松开且未伴随普通键（单按 Shift 切输入法、
    // 单按 Alt 呼出菜单栏），在松开瞬间补发一次独立按键
    if (heldModifiers.size === 0 && !modifierComboSent) {
        sendKeys([MODIFIER_MAP[e.key]]);
    }
});

// 窗口失焦时清空修饰键状态（防止卡键）
window.addEventListener('blur', function() {
    heldModifiers.clear();
    modifierComboSent = false;
});
