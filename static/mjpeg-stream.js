var streamUrl = '/screenshot/api/stream';

var streamImg = document.getElementById('mjpeg-stream');
var fpsDisplay = document.getElementById('fps-display');

var frameCount = 0;
var lastFpsUpdate = Date.now();

streamImg.src = streamUrl;

function updateFps() {
    var now = Date.now();
    if (now - lastFpsUpdate >= 1000) {
        fpsDisplay.textContent = 'FPS: ' + frameCount;
        frameCount = 0;
        lastFpsUpdate = now;
    }
}

// 使用定时器检测帧变化并计算 FPS
setInterval(function() {
    if (streamImg.complete && streamImg.naturalWidth > 0) {
        frameCount++;
    }
    updateFps();
}, 100);

// 连接中断时自动重连
streamImg.onerror = function() {
    console.log('流连接中断，尝试重新连接...');
    setTimeout(function() {
        streamImg.src = streamUrl + '?t=' + Date.now();
    }, 1000);
};
