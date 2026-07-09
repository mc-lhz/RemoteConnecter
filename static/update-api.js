var updateBtn = document.getElementById('update-btn');
var updateMessage = document.getElementById('update-message');
var reconnectMessage = document.getElementById('reconnect-message');
var updateApi = '/api/update';

function showMessage(text, type) {
    updateMessage.textContent = text;
    updateMessage.className = '';
    if (type === 'success') {
        updateMessage.classList.add('success');
    } else if (type === 'error') {
        updateMessage.classList.add('error');
    } else {
        updateMessage.style.display = 'block';
        updateMessage.style.background = 'rgba(59, 130, 246, 0.1)';
        updateMessage.style.color = '#93c5fd';
        updateMessage.style.border = '1px solid rgba(59, 130, 246, 0.3)';
        return;
    }
}

function startReconnect() {
    reconnectMessage.style.display = 'block';
    var count = 3;
    var countdown = setInterval(function() {
        reconnectMessage.textContent = count + ' 秒后尝试重连...';
        count--;
        if (count < 0) {
            clearInterval(countdown);
            doReconnect();
        }
    }, 1000);
}

function doReconnect() {
    var reconnectTimes = 0;
    var maxRetries = 30;

    function tryReconnect() {
        reconnectTimes++;
        reconnectMessage.textContent = '重连中... 第 ' + reconnectTimes + ' 次';

        $.get('/')
            .done(function() {
                reconnectMessage.textContent = '重连成功！即将跳转...';
                setTimeout(function() {
                    window.location.href = '/';
                }, 1000);
            })
            .fail(function() {
                if (reconnectTimes >= maxRetries) {
                    reconnectMessage.textContent = '重连失败，已失去对系统的访问权限';
                } else {
                    setTimeout(tryReconnect, 1000);
                }
            });
    }

    tryReconnect();
}

updateBtn.addEventListener('click', function() {
    var updateUrl = document.getElementById('update-url').value;

    if (!updateUrl) {
        showMessage('请输入更新URL', 'error');
        return;
    }

    updateBtn.disabled = true;
    updateBtn.textContent = '更新中...';
    showMessage('正在下载更新包...', 'info');

    $.get(updateApi, { updateUrl: updateUrl }, function(data) {
        console.log(data);
        if (data.status === 'success') {
            showMessage('更新成功，' + data.message, 'success');
            startReconnect();
        } else {
            showMessage('更新失败，' + data.message, 'error');
            updateBtn.disabled = false;
            updateBtn.textContent = '开始更新';
        }
    }).fail(function(xhr, status, error) {
        showMessage('请求失败: ' + error, 'error');
        updateBtn.disabled = false;
        updateBtn.textContent = '开始更新';
    });
});
