// 页面切换逻辑
document.addEventListener('DOMContentLoaded', function() {
    const currentTime = document.getElementById('currentTime');

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
                // 发送POST请求到后端执行命令
                $.post('/api/command', { cmd: command }, function(data) {
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

    // 远程控制按钮
    function setupInteractiveButtons() {
        document.querySelectorAll('.control-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const action = this.querySelector('span').textContent;
                if (action === '实时屏幕') {
                    window.location.href = '/screenshot';
                }
            });
        });
    }

    // 初始化所有功能
    updateTime();
    setupTabSwitching();
    setupCommandExecution();
    setupInteractiveButtons();

    // 每秒更新时间
    setInterval(updateTime, 1000);
});
