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
        if (!document.hidden) {
            streamImg.src = streamUrl + '?t=' + Date.now();
        }
    }, 1000);
};

// 页面隐藏时断开流（服务端生成器随连接关闭终止，停止抓屏编码），
// 回到前台重连——公网/后台标签页不再白白消耗带宽。
// 注意不能 src=''：空串会按标准解析成当前页面 URL（把 HTML 当图片
// 触发 onerror），removeAttribute 才是干净的断流
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        streamImg.removeAttribute('src');
        console.log('页面已隐藏，暂停屏幕流');
    } else {
        streamImg.src = streamUrl + '?t=' + Date.now();
        console.log('页面回到前台，恢复屏幕流');
    }
});
