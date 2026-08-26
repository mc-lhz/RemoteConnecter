(function() {
    'use strict';

    const widget = document.getElementById('bilimusic-widget');
    const header = document.getElementById('widget-header');
    const toggleIcon = document.getElementById('toggle-icon');
    const searchInput = document.getElementById('search-input');
    const searchBtn = document.getElementById('search-btn');
    const resultList = document.getElementById('result-list');
    const nowPlaying = document.getElementById('now-playing');
    const progressSlider = document.getElementById('progress-slider');
    const timeLabel = document.getElementById('time-label');
    const pauseBtn = document.getElementById('pause-btn');
    const stopBtn = document.getElementById('stop-btn');
    const useOldApiBtn = document.getElementById('use-old-api-btn');

    let currentBvid = null;
    let isPlaying = false;
    let isPaused = false;
    let isStopped = true;
    let songDuration = 0;
    let progressTimer = null;

    const API_BASE = '/bilimusic/api';

    function formatTime(seconds) {
        if (isNaN(seconds) || !isFinite(seconds)) seconds = 0;
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }

    function escapeHtml(text) {
        if (text == null) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function callApi(action, data = {}) {
        return fetch(`${API_BASE}/${action}`, {
            method: action === 'status' ? 'GET' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: action !== 'status' ? JSON.stringify(data) : undefined
        }).then(res => res.json());
    }

    function playSong(bvid, title, author) {
        currentBvid = bvid;
        nowPlaying.textContent = `${title} - ${author}`;
        callApi('control', { operation: 'play', bvid: bvid })
            .then(res => {
                if (res.success) {
                    isPlaying = true;
                    isPaused = false;
                    isStopped = false;
                    pauseBtn.textContent = '⏸';

                    songDuration = res.duration || 0;
                    progressSlider.max = songDuration > 0 ? songDuration : 100;
                    progressSlider.value = 0;
                    timeLabel.textContent = `00:00 / ${formatTime(songDuration)}`;

                    startProgressTimer();
                } else {
                    nowPlaying.textContent = '播放失败: ' + (res.error || '未知错误');
                }
            })
            .catch(err => {
                nowPlaying.textContent = '请求失败: ' + err.message;
            });
    }

    function togglePause() {
        if (isStopped || !currentBvid) return;
        const op = isPaused ? 'resume' : 'pause';
        callApi('control', { operation: op })
            .then(res => {
                if (res.success) {
                    isPaused = !isPaused;
                    isPlaying = !isPaused;
                    pauseBtn.textContent = isPaused ? '▶' : '⏸';
                    if (isPaused) {
                        stopProgressTimer();
                    } else {
                        startProgressTimer();
                    }
                }
            });
    }

    function startProgressTimer() {
        stopProgressTimer();
        progressTimer = setInterval(() => {
            if (!isPlaying || isPaused || isStopped) return;
            const current = parseFloat(progressSlider.value) || 0;
            if (current >= songDuration) {
                stopProgressTimer();
                isPlaying = false;
                isStopped = true;
                return;
            }
            progressSlider.value = current + 1;
            timeLabel.textContent = `${formatTime(current + 1)} / ${formatTime(songDuration)}`;
        }, 1000);
    }

    function stopProgressTimer() {
        if (progressTimer) {
            clearInterval(progressTimer);
            progressTimer = null;
        }
    }

    function stopSong() {
        callApi('control', { operation: 'stop' })
            .then(res => {
                if (res.success) {
                    isPlaying = false;
                    isPaused = false;
                    isStopped = true;
                    pauseBtn.textContent = '⏸';
                    progressSlider.value = 0;
                    timeLabel.textContent = `00:00 / ${formatTime(songDuration)}`;
                    nowPlaying.textContent = '已停止';
                    stopProgressTimer();
                }
            });
    }

    function performSearch(keyword) {
        const keywordStr = keyword.trim();
        if (!keywordStr) {
            resultList.innerHTML = `<div class="empty-tip">输入关键词搜索</div>`;
            return;
        }

        callApi('search', { keyword: keywordStr ,useOldApi: useOldApiBtn.checked})
            .then(res => {
                if (!res.success) {
                    resultList.innerHTML = `<div class="empty-tip">搜索失败: ${res.error}</div>`;
                    return;
                }
                const data = res.data || [];
                if (data.length === 0) {
                    resultList.innerHTML = `<div class="empty-tip">未找到相关视频</div>`;
                    return;
                }

                let html = '';
                data.forEach(item => {
                    const bvid = item.bvid || item.BVID || '';
                    const title = item.title || item.Title || '未知标题';
                    const author = item.author || item.Author || '未知作者';
                    html += `
                        <div class="result-item" data-bvid="${escapeHtml(bvid)}" data-title="${escapeHtml(title)}" data-author="${escapeHtml(author)}">
                            <div class="info">
                                <span class="title">${escapeHtml(title)}</span>
                                <span class="author">${escapeHtml(author)}</span>
                            </div>
                            <span class="play-icon">▶</span>
                        </div>
                    `;
                });
                resultList.innerHTML = html;

                resultList.querySelectorAll('.result-item').forEach(el => {
                    el.addEventListener('click', function() {
                        playSong(this.dataset.bvid, this.dataset.title, this.dataset.author);
                    });
                });
            })
            .catch(err => {
                resultList.innerHTML = `<div class="empty-tip">网络错误: ${err.message}</div>`;
            });
    }

    function seekTime(time) {
        const seekSeconds = parseFloat(time) || 0;
        callApi('control', { operation: 'seek', time: seekSeconds })
            .then(res => {
                if (res.success) {
                    progressSlider.value = seekSeconds;
                    timeLabel.textContent = `${formatTime(seekSeconds)} / ${formatTime(songDuration)}`;
                } else {
                    nowPlaying.textContent = '跳转失败: ' + (res.error || '未知错误');
                }
            });
    }
    function notifyHeight() {
        var collapsed = widget.classList.contains('collapsed');
        var height = collapsed ? 56 : 520;
        if (window.parent && window.parent !== window) {
            window.parent.postMessage({ type: 'bilimusic-height', height: height, collapsed: collapsed }, '*');
        }
    }

    header.addEventListener('click', function(e) {
        if (e.target.closest('button')) return;
        widget.classList.toggle('collapsed');
        toggleIcon.textContent = widget.classList.contains('collapsed') ? '▼' : '▲';
        notifyHeight();
    });

    // 初始通知一次高度
    setTimeout(notifyHeight, 100);

    searchBtn.addEventListener('click', function() {
        performSearch(searchInput.value);
    });

    searchInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            searchBtn.click();
        }
    });

    pauseBtn.addEventListener('click', togglePause);
    stopBtn.addEventListener('click', stopSong);
    // 进度条手动进度
    progressSlider.addEventListener('input', function() {
        console.log(this.value);
        seekTime(this.value);
    });
    resultList.innerHTML = `<div class="empty-tip">输入关键词搜索</div>`;
    nowPlaying.textContent = '未播放';
    progressSlider.value = 0;
    timeLabel.textContent = '00:00 / 00:00';

    // 搜索后重新计算高度
    var originalPerformSearch = performSearch;
    performSearch = function(keyword) {
        originalPerformSearch(keyword);
        setTimeout(notifyHeight, 300);
    };

    console.log('Bilimusic 已启动');
})();