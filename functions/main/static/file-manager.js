// 全局变量保存当前路径信息
let currentPathInfo = null;

// 下载文件
function getFileList(filePath, callback) {
    $.get('/download/api', { path: filePath }, function(data) {
        callback(data);
    });
}
// 从完整路径取文件名（保留原始大小写；盘符根如 C:\ 显示为 C:）
function baseNameOf(p) {
    const parts = String(p || '').split(/[\\/]/).filter(Boolean);
    return parts.length ? parts[parts.length - 1] : String(p || '');
}

// 填充文件列表（仅显示文件名，当前文件夹路径显示在顶部路径栏）
function putFileBox(filePath, fileJson, fileGrid) {
    if (fileJson && fileJson["fileList"]) {
        currentPathInfo = fileJson;
        const pathBar = document.getElementById('current-path');
        if (pathBar) {
            pathBar.textContent = fileJson["currentPath"] || filePath || '/';
            pathBar.title = pathBar.textContent;
        }
        if (fileJson["fileList"].length > 0) {
            fileJson["fileList"].forEach(item => {
                if (item["type"] == "folder" || item["type"] == "file") {
                    const fileBox = document.createElement('div');
                    fileBox.classList.add('file-box');
                    fileBox.dataset.path = item["path"];
                    fileBox.dataset.type = item["type"];
                    fileBox.innerHTML = `<i class="file-icon">${item["type"] == 'folder' ? '📁' : '📄'}</i>`;
                    const label = document.createElement('div');
                    label.textContent = baseNameOf(item["path"]) || item["name"] || item["path"];
                    fileBox.appendChild(label);
                    fileBox.addEventListener('click', function() {
                        if (this.dataset.type == 'folder') {
                            updateFileList(this.dataset.path);
                        } else {
                            window.open(`/download?path=${encodeURIComponent(this.dataset.path)}`);
                        }
                    });
                    fileGrid.appendChild(fileBox);
                }
            });
        } else {
            fileGrid.innerHTML = `<div class="no-files">暂无文件</div>`;
        }
    }
}

// 初始化文件列表
function initFile() {
    let rootPath = String.raw`/`;
    let fileGrid = document.querySelector('.file-grid');
    getFileList(rootPath, function(fileJson) {
        putFileBox(rootPath, fileJson, fileGrid);
    });
}

// 点击时获取新列表
function updateFileList(filePath) {
    let fileGrid = document.querySelector('.file-grid');
    fileGrid.innerHTML = '';
    getFileList(filePath, function(fileJson) {
        putFileBox(filePath, fileJson, fileGrid);
    });
}

// 处理返回按钮点击事件
var returnBtn = document.getElementById('return-btn');
returnBtn.addEventListener('click', function() {
    if (currentPathInfo && currentPathInfo["parentPath"]) {
        updateFileList(currentPathInfo["parentPath"]);
    }
});

initFile();

// 上传文件
var localUploadBtn = document.getElementById('upload-btn');
localUploadBtn.addEventListener('click', function() {
    // Create hidden file input element
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.style.display = 'none';
    document.body.appendChild(fileInput);

    // Trigger file selection dialog
    fileInput.click();

    // Handle file selection
    fileInput.addEventListener('change', function() {
        const file = this.files[0];
        if (file) {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('path', currentPathInfo ? currentPathInfo["currentPath"] : '/');
            formData.append('remote', 'false');
            formData.append('execute', document.getElementById('execute-checkbox').checked ? 'true' : 'false');
            formData.append('tempdir', document.getElementById('tempdir-checkbox').checked ? 'true' : 'false');

            $.ajax({
                url: '/upload',
                type: 'POST',
                data: formData,
                processData: false,
                contentType: false,
                success: function(response) {
                    alert('文件上传成功: ' + response["filename"]);
                    updateFileList(currentPathInfo ? currentPathInfo["currentPath"] : '/');
                },
                error: function(xhr) {
                    var msg = xhr.responseJSON ? xhr.responseJSON.error : xhr.statusText;
                    alert('文件上传失败: ' + msg);
                    updateFileList(currentPathInfo ? currentPathInfo["currentPath"] : '/');
                }
            });
        }
        // Clean up
        document.body.removeChild(fileInput);
    });
});

var remoteUploadBtn = document.getElementById('remote-upload-btn');
remoteUploadBtn.addEventListener('click', function() {
    // 弹出输入框输入 URL
    var fileUrl = prompt('请输入要下载的文件 URL:');
    if (!fileUrl) {
        alert('请输入正确的文件 URL');
        return;
    }
    // 保存路径
    var savePath = currentPathInfo["currentPath"];
    // 使用远程地址上传文件，upload接口
    $.ajax({
        url: '/upload',
        type: 'POST',
        data: {
            remote: 'true',
            url: fileUrl,
            path: savePath,
            execute: document.getElementById('execute-checkbox').checked ? 'true' : 'false',
            tempdir: document.getElementById('tempdir-checkbox').checked ? 'true' : 'false'
        },
        success: function(response) {
            alert('远程文件上传成功: ' + response["filename"]);
            updateFileList(currentPathInfo ? currentPathInfo["currentPath"] : '/');
        },
        error: function(xhr) {
            var msg = xhr.responseJSON ? xhr.responseJSON.error : xhr.statusText;
            alert('远程文件上传失败: ' + msg);
            updateFileList(currentPathInfo ? currentPathInfo["currentPath"] : '/');
        }
    });
});
