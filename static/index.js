// 设备检测与页面切换逻辑
document.addEventListener('DOMContentLoaded', function() {
    const deviceInfo = document.getElementById('deviceInfo');
    const currentTime = document.getElementById('currentTime');

    // 检测设备类型和屏幕方向
    function detectDeviceAndLayout() {
        const width = window.innerWidth;
        const height = window.innerHeight;
        const aspectRatio = width / height;

        // 判断是横屏设备（如词典笔）还是竖屏手机
        if (aspectRatio >= 2) { // 宽高比 >= 2: 横屏模式
            deviceInfo.textContent = '横屏模式 (词典笔)';
            document.body.classList.add('landscape');
            document.body.classList.remove('portrait');
        } else { // 竖屏模式
            deviceInfo.textContent = '竖屏模式 (手机)';
            document.body.classList.add('portrait');
            document.body.classList.remove('landscape');
        }
    }

    // 更新当前时间
    function updateTime() {
        const now = new Date();
        const timeStr = now.toLocaleTimeString('zh-CN');
        if (currentTime) {
            currentTime.textContent = timeStr;
        }
    }

    // 页面切换功能 (同时处理侧边栏和底部导航)
    function setupTabSwitching() {
        // 获取所有可切换标签的按钮
        const allNavButtons = document.querySelectorAll('.nav-item, .nav-btn');
        const allTabs = document.querySelectorAll('.tab-content');

        allNavButtons.forEach(button => {
            button.addEventListener('click', function() {
                const targetTabId = this.getAttribute('data-tab');

                // 更新活跃按钮
                allNavButtons.forEach(btn => btn.classList.remove('active'));
                this.classList.add('active');

                // 切换对应页面
                allTabs.forEach(tab => {
                    tab.classList.remove('active');
                });
                document.getElementById(targetTabId).classList.add('active');
            });
        });
    }

    // 命令执行功能
    function setupCommandExecution() {
        const executeBtn = document.querySelector('.execute-btn');
        const commandInput = document.querySelector('.command-input');
        const outputDiv = document.querySelector('.output');

        if (executeBtn && commandInput && outputDiv) {
            executeBtn.addEventListener('click', function() {
                const command = commandInput.value.trim();

                if (!command) {
                    alert('请输入有效命令');
                    return;
                }
                $.post('/terminal', { cmd: command }, function(data) {
                    outputDiv.innerHTML = data;
                });

                commandInput.value = ''; // 清空输入
            });

            // 允许按Enter键执行
            commandInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    executeBtn.click();
                }
            });
        }
    }

    // 模拟下载和远程控制点击
    function setupInteractiveButtons() {
        // 远程控制按钮
        document.querySelectorAll('.control-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const action = this.querySelector('span').textContent;
                if (action === '键鼠控制') {
                    window.location.href = '/control';
                } else if (action === '实时屏幕') {
                    window.location.href = '/screenshot';
                }
            });
        });
    }

    // 初始化所有功能
    detectDeviceAndLayout();
    updateTime();
    setupTabSwitching();
    setupCommandExecution();
    setupInteractiveButtons();

    // 监听窗口变化，自动切换布局
    window.addEventListener('resize', detectDeviceAndLayout);

    // 每秒更新时间
    setInterval(updateTime, 1000);
});
