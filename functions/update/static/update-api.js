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
// ===== 检查更新 / 节点池一键更新 =====
var checkUpdateBtn = document.getElementById('check-update-btn');
var nodepoolUpdateBtn = document.getElementById('nodepool-update-btn');
var checkUpdateMessage = document.getElementById('check-update-message');
var currentVersionBox = document.getElementById('current-version');

if (checkUpdateBtn) {
    checkUpdateBtn.addEventListener('click', function() {
        checkUpdateBtn.disabled = true;
        checkUpdateBtn.textContent = '检查中...';
        showMessage(checkUpdateMessage, '正在获取最新发行版信息...', 'info');

        $.get('/update/api/check', function(data) {
            checkUpdateBtn.disabled = false;
            checkUpdateBtn.textContent = '检查更新';
            if (currentVersionBox && data.current) {
                currentVersionBox.textContent = data.current;
            }
            if (data.error) {
                showMessage(checkUpdateMessage, data.error, 'error');
                return;
            }
            if (data.updateAvailable) {
                showMessage(checkUpdateMessage,
                    '发现新版本 ' + data.latest + '（当前 ' + data.current + '）', 'success');
                nodepoolUpdateBtn.style.display = '';
            } else {
                showMessage(checkUpdateMessage,
                    '已是最新版本（' + data.current + '）', 'success');
                nodepoolUpdateBtn.style.display = 'none';
            }
        }).fail(function(xhr) {
            checkUpdateBtn.disabled = false;
            checkUpdateBtn.textContent = '检查更新';
            var msg = xhr.responseJSON && xhr.responseJSON.error ? xhr.responseJSON.error : xhr.statusText;
            showMessage(checkUpdateMessage, '检查失败: ' + msg, 'error');
        });
    });
}

if (nodepoolUpdateBtn) {
    nodepoolUpdateBtn.addEventListener('click', function() {
        if (!window.confirm('将通过加速节点下载最新版本并自动替换重启，继续吗？')) {
            return;
        }
        nodepoolUpdateBtn.disabled = true;
        nodepoolUpdateBtn.textContent = '更新中...';
        showMessage(checkUpdateMessage, '正在测速并下载（节点池加速，可能需要数分钟）...', 'info');

        $.post(updateApi, { updateMethod: 'nodepool' }, function(data) {
            if (data.status === 'success') {
                showMessage(checkUpdateMessage, '更新成功，' + data.message, 'success');
                startReconnect();
            } else {
                showMessage(checkUpdateMessage, '更新失败，' + data.message, 'error');
                nodepoolUpdateBtn.disabled = false;
                nodepoolUpdateBtn.textContent = '一键更新';
            }
        }).fail(function(xhr, status, error) {
            var msg = xhr.responseJSON && xhr.responseJSON.message ? xhr.responseJSON.message : error;
            showMessage(checkUpdateMessage, '请求失败: ' + msg, 'error');
            nodepoolUpdateBtn.disabled = false;
            nodepoolUpdateBtn.textContent = '一键更新';
        });
    });
}
