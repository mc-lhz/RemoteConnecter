var streamImg = document.getElementById('mjpeg-stream');
var fpsDisplay = document.getElementById('fps-display');

// ---- 画质预设（直接影响公网流畅性: fps/quality/scale；auto=1 消费速度自适应）----
var PRESETS = {
    auto: { label: '自动（推荐）', fps: 10, quality: 95, scale: 1, auto: 1 },
    smooth: { label: '流畅', fps: 6, quality: 55, scale: 0.55 },
    standard: { label: '标准', fps: 10, quality: 75, scale: 1 },
    hd: { label: '高清', fps: 15, quality: 90, scale: 1 }
};
var PRESET_KEY = 'rc-screen-preset';
var currentPreset = 'auto';
try {
    if (PRESETS[localStorage.getItem(PRESET_KEY)]) { currentPreset = localStorage.getItem(PRESET_KEY); }
} catch (e) { /* ignore */ }

var streamActive = true;
var frameCount = 0;
var lastFpsUpdate = Date.now();

function buildStreamUrl() {
    var p = PRESETS[currentPreset];
    return '/screenshot/api/stream?fps=' + p.fps + '&quality=' + p.quality +
        '&scale=' + p.scale + (p.auto ? '&auto=1' : '&auto=0') + '&t=' + Date.now();
}

function connectStream() {
    streamActive = true;
    streamImg.src = buildStreamUrl();
}

function disconnectStream() {
    streamActive = false;
    streamImg.removeAttribute('src');
}

// 画质选择器
(function buildPresetPicker() {
    var picker = document.createElement('select');
    picker.id = 'rc-quality-select';
    picker.title = '画质 (流畅省带宽 / 高清更清晰)';
    Object.keys(PRESETS).forEach(function (key) {
        var option = document.createElement('option');
        option.value = key;
        option.textContent = PRESETS[key].label;
        if (key === currentPreset) { option.selected = true; }
        picker.appendChild(option);
    });
    picker.addEventListener('change', function () {
        if (!PRESETS[picker.value]) { return; }
        currentPreset = picker.value;
        try { localStorage.setItem(PRESET_KEY, currentPreset); } catch (e) { /* ignore */ }
        disconnectStream();
        connectStream();
    });
    document.body.appendChild(picker);
})();

function updateFps() {
    var now = Date.now();
    if (now - lastFpsUpdate >= 1000) {
        fpsDisplay.textContent = 'FPS: ' + frameCount;
        frameCount = 0;
        lastFpsUpdate = now;
    }
}

// 使用定时器检测帧变化并计算 FPS
setInterval(function () {
    if (streamImg.complete && streamImg.naturalWidth > 0) {
        frameCount++;
    }
    updateFps();
}, 100);

// 连接中断时自动重连（页面隐藏暂停期间不重连）
streamImg.onerror = function () {
    if (!streamActive) { return; }
    console.log('流连接中断，尝试重新连接...');
    setTimeout(function () {
        if (streamActive) { streamImg.src = buildStreamUrl(); }
    }, 1000);
};

// 页面隐藏 → 断开释放服务端采集/编码; 恢复 → 重连
document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
        disconnectStream();
    } else {
        connectStream();
    }
});

connectStream();