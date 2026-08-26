var remoteUpdateBtn = document.getElementById('remote-update-btn');
var localUpdateBtn = document.getElementById('local-update-btn');
var remoteUpdateMessage = document.getElementById('remote-update-message');
var localUpdateMessage = document.getElementById('local-update-message');
// 统一重连消息框（远程/本地更新共用）
var reconnectMessage = document.getElementById('reconnect-message');
var updateApi = '/update/api/update';

// 显示消息：success / error / info
function showMessage(divObj, text, type) {
    divObj.textContent = text;
    divObj.className = '';
    if (type === 'success') {
        divObj.classList.add('success');
    } else if (type === 'error') {
        divObj.classList.add('error');
    } else {
        // info 或默认
        divObj.classList.add('info');
    }
}

// 更新成功后启动重连倒计时
function startReconnect() {
    reconnectMessage.style.display = 'block';
    reconnectMessage.className = '';
    reconnectMessage.classList.add('info');
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

// 执行重连请求
function doReconnect() {
    var reconnectTimes = 0;
    var maxRetries = 10;

    function tryReconnect() {
        reconnectTimes++;
        reconnectMessage.textContent = '重连中... 第 ' + reconnectTimes + ' 次';

        $.ajax({
            url: '/',
            type: 'GET',
            timeout: 3000
        })
            .done(function() {
                reconnectMessage.className = '';
                reconnectMessage.classList.add('success');
                reconnectMessage.textContent = '重连成功！即将跳转...';
                setTimeout(function() {
                    window.location.href = '/';
                }, 1000);
            })
            .fail(function() {
                if (reconnectTimes >= maxRetries) {
                    reconnectMessage.className = '';
                    reconnectMessage.classList.add('error');
                    reconnectMessage.textContent = '重连失败，已失去对系统的访问权限';
                } else {
                    setTimeout(tryReconnect, 1000);
                }
            });
    }

    tryReconnect();
}

// ===== 远程更新 =====
remoteUpdateBtn.addEventListener('click', function() {
    var updateUrl = document.getElementById('update-url').value;

    if (!updateUrl) {
        showMessage(remoteUpdateMessage, '请输入更新URL', 'error');
        return;
    }

    remoteUpdateBtn.disabled = true;
    remoteUpdateBtn.textContent = '更新中...';
    showMessage(remoteUpdateMessage, '正在下载更新包...', 'info');

    $.post(updateApi, { updateMethod: 'remote', updateUrl: updateUrl }, function(data) {
        console.log(data);
        if (data.status === 'success') {
            showMessage(remoteUpdateMessage, '更新成功，' + data.message, 'success');
            startReconnect();
        } else {
            showMessage(remoteUpdateMessage, '更新失败，' + data.message, 'error');
            remoteUpdateBtn.disabled = false;
            remoteUpdateBtn.textContent = '开始更新';
        }
    }).fail(function(xhr, status, error) {
        showMessage(remoteUpdateMessage, '请求失败: ' + error, 'error');
        remoteUpdateBtn.disabled = false;
        remoteUpdateBtn.textContent = '开始更新';
    });
});

// ===== 本地更新 =====
localUpdateBtn.addEventListener('click', function() {
    var updaterFileInput = document.getElementById('update-file');
    var updaterFile = updaterFileInput.files[0];

    if (!updaterFile) {
        showMessage(localUpdateMessage, '请选择更新包', 'error');
        return;
    }

    localUpdateBtn.disabled = true;
    localUpdateBtn.textContent = '上传中...';
    showMessage(localUpdateMessage, '正在上传更新包...', 'info');

    var updateFormData = new FormData();
    updateFormData.append('updateMethod', 'local');
    updateFormData.append('file', updaterFile);

    $.ajax({
        url: updateApi,
        type: 'POST',
        data: updateFormData,
        processData: false,
        contentType: false,
        success: function(data) {
            console.log(data);
            if (data.status === 'success') {
                showMessage(localUpdateMessage, '更新成功，' + data.message, 'success');
                startReconnect();
            } else {
                showMessage(localUpdateMessage, '更新失败，' + data.message, 'error');
                localUpdateBtn.disabled = false;
                localUpdateBtn.textContent = '开始更新';
            }
        },
        error: function(xhr, status, error) {
            showMessage(localUpdateMessage, '请求失败: ' + error, 'error');
            localUpdateBtn.disabled = false;
            localUpdateBtn.textContent = '开始更新';
        }
    });
});