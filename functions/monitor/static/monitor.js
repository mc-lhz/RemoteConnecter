(function () {
    'use strict';

    var $ = function (id) { return document.getElementById(id); };
    var toastTimer = 0;

    function toast(text) {
        var el = $('toast');
        el.textContent = text;
        el.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { el.hidden = true; }, 2600);
    }

    async function api(url, options) {
        var response = await fetch(url, options);
        var data = await response.json().catch(function () { return {}; });
        if (!response.ok) {
            throw new Error(data.message || ('HTTP ' + response.status));
        }
        return data;
    }

    function formatBytes(num) {
        var value = Number(num) || 0;
        var units = ['B', 'KB', 'MB', 'GB', 'TB'];
        var i = 0;
        while (value >= 1024 && i < units.length - 1) { value /= 1024; i += 1; }
        return (i === 0 ? value : value.toFixed(1)) + ' ' + units[i];
    }

    function formatUptime(seconds) {
        var d = Math.floor(seconds / 86400);
        var h = Math.floor((seconds % 86400) / 3600);
        var m = Math.floor((seconds % 3600) / 60);
        if (d > 0) { return d + ' 天 ' + h + ' 小时 ' + m + ' 分'; }
        if (h > 0) { return h + ' 小时 ' + m + ' 分'; }
        return m + ' 分';
    }

    var history = { cpu: [], mem: [] };
    var HISTORY_MAX = 60;

    function drawSparkline(canvas, points, color) {
        var ctx = canvas.getContext('2d');
        var w = canvas.width;
        var h = canvas.height;
        ctx.clearRect(0, 0, w, h);
        if (points.length < 2) { return; }
        var stepX = w / (HISTORY_MAX - 1);
        ctx.beginPath();
        points.forEach(function (value, index) {
            var x = index * stepX;
            var y = h - (Math.max(0, Math.min(100, value)) / 100) * (h - 2) - 1;
            if (index === 0) { ctx.moveTo(x, y); } else { ctx.lineTo(x, y); }
        });
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.lineTo((points.length - 1) * stepX, h);
        ctx.lineTo(0, h);
        ctx.closePath();
        ctx.fillStyle = color.replace('rgb', 'rgba').replace(')', ', 0.14)');
        ctx.fill();
    }

    function pushHistory(key, value, canvasId, color) {
        var list = history[key];
        list.push(Number(value) || 0);
        if (list.length > HISTORY_MAX) { list.shift(); }
        var canvas = $(canvasId);
        if (canvas) { drawSparkline(canvas, list, color); }
    }

    async function refreshStats() {
        try {
            var data = await api('/monitor/api/stats');
            $('st-host').textContent = data.host || '--';
            $('st-uptime').textContent = formatUptime(data.uptimeSeconds || 0);
            $('st-cpu').textContent = (data.cpuPercent || 0) + '%';
            pushHistory('cpu', data.cpuPercent, 'cpu-chart', 'rgb(31, 111, 235)');
            var mem = data.memory || {};
            $('st-mem').textContent = mem.percent + '% 可用 ' + formatBytes(mem.free || 0);
            pushHistory('mem', mem.percent, 'mem-chart', 'rgb(15, 157, 88)');
            var diskMap = {};
            (data.disks || []).forEach(function (d) {
                diskMap[d.drive.charAt(0).toUpperCase()] = d;
            });
            ['C', 'D'].forEach(function (letter, idx) {
                var el = $('st-disk-' + letter.toLowerCase());
                var disk = diskMap[letter];
                if (disk) {
                    el.hidden = false;
                    el.querySelector('.stat-value').textContent = formatBytes(disk.free) + ' 可用';
                } else if (idx === 1 && !disk) {
                    var any = (data.disks || [])[1];
                    if (any) {
                        el.hidden = false;
                        el.querySelector('.stat-label').textContent = any.drive;
                        el.querySelector('.stat-value').textContent = formatBytes(any.free) + ' 可用';
                    } else {
                        el.hidden = true;
                    }
                }
            });
        } catch (err) { /* 下次轮询重试 */ }
    }

    async function refreshPills() {
        try {
            var data = await api('/monitor/api/overview');
            var box = $('pills');
            box.textContent = '';
            (data.pills || []).forEach(function (p) {
                var span = document.createElement('span');
                span.className = 'pill' + (p.state !== '正常' ? ' warn' : '');
                span.textContent = p.name + '·' + p.state + (p.detail ? '·' + p.detail : '');
                box.appendChild(span);
            });
            if (data.version) {
                var v = document.createElement('span');
                v.className = 'pill';
                v.textContent = data.version;
                box.appendChild(v);
            }
        } catch (err) { /* 忽略 */ }
    }

    document.querySelectorAll('[data-action]').forEach(function (btn) {
        btn.addEventListener('click', async function () {
            var action = btn.getAttribute('data-action');
            if (action === 'restart' || action === 'shutdown') {
                if (!confirm(action === 'restart'
                    ? '确认 5 秒后重启本机？远程连接将中断。'
                    : '确认 5 秒后关机本机？远程连接将中断。')) {
                    return;
                }
            }
            try {
                var data = await api('/monitor/api/action', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ type: action })
                });
                toast(data.message || '已执行');
            } catch (err) {
                toast('执行失败: ' + err.message);
            }
        });
    });

    var currentTab = 'processes';
    document.querySelectorAll('.tab').forEach(function (tab) {
        tab.addEventListener('click', function () {
            document.querySelectorAll('.tab').forEach(function (t) { t.classList.remove('active'); });
            document.querySelectorAll('.pane').forEach(function (p) { p.classList.remove('active'); });
            tab.classList.add('active');
            currentTab = tab.getAttribute('data-tab');
            $('pane-' + currentTab).classList.add('active');
            refreshTab();
        });
    });

    var procQuery = '';
    $('proc-search').addEventListener('input', function () {
        procQuery = this.value.trim().toLowerCase();
        if (currentTab === 'processes') { refreshTab(); }
    });
    $('proc-search').addEventListener('keydown', function (event) {
        if (event.key === 'Enter') { refreshTab(); }
    });

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) { node.className = className; }
        if (text !== undefined) { node.textContent = text; }
        return node;
    }

    function rowButton(label, handler, cls) {
        var btn = el('button', cls || 'kill', label);
        btn.addEventListener('click', handler);
        return btn;
    }

    async function killAndRefresh(payload, hint) {
        if (hint && !confirm(hint)) { return; }
        try {
            var data = await api('/monitor/api/kill', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            toast(data.message);
            refreshTab();
        } catch (err) {
            toast('执行失败: ' + err.message);
        }
    }

    function renderProcesses(items) {
        var list = $('proc-list');
        list.textContent = '';
        if (!items.length) {
            list.appendChild(el('div', 'empty', '没有匹配的进程'));
            return;
        }
        items.forEach(function (item) {
            var row = el('div', 'row');
            var meta = el('div', 'meta');
            meta.appendChild(el('div', 'name', item.name + (item.count > 1 ? ' ×' + item.count : '')));
            var subs = [formatBytes(item.mem)];
            if (item.count === 1) { subs.push('PID ' + item.pids[0].pid); }
            meta.appendChild(el('div', 'sub', subs.join(' · ')));
            row.appendChild(meta);
            if (item.count === 1) {
                row.appendChild(rowButton('结束', function () {
                    killAndRefresh({ pid: item.pids[0].pid }, '结束 ' + item.name + ' (PID ' + item.pids[0].pid + ')？');
                }));
            } else {
                row.appendChild(rowButton('全部结束', function () {
                    killAndRefresh({ name: item.name }, '结束全部 ' + item.count + ' 个 ' + item.name + '？');
                }));
            }
            list.appendChild(row);
        });
    }

    function renderWindows(items) {
        var list = $('win-list');
        list.textContent = '';
        if (!items.length) {
            list.appendChild(el('div', 'empty', '没有可见窗口'));
            return;
        }
        items.forEach(function (item) {
            var row = el('div', 'row');
            var meta = el('div', 'meta');
            meta.appendChild(el('div', 'name', item.title));
            meta.appendChild(el('div', 'sub', (item.exe || '未知进程') + ' · PID ' + item.pid));
            row.appendChild(meta);
            var focus = rowButton('激活', function () { windowOp(item, 'focus'); }, 'kill');
            row.appendChild(focus);
            row.appendChild(rowButton('最小化', function () { windowOp(item, 'min'); }, 'kill'));
            row.appendChild(rowButton('关闭', function () { windowOp(item, 'close'); }, 'kill'));
            list.appendChild(row);
        });
    }

    async function windowOp(item, op) {
        try {
            var data = await api('/monitor/api/window', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hwnd: item.hwnd, op: op })
            });
            toast(data.message);
        } catch (err) {
            toast('执行失败: ' + err.message);
        }
    }

    function renderApps(items) {
        var list = $('app-list');
        list.textContent = '';
        if (!items.length) {
            list.appendChild(el('div', 'empty', '没有找到应用'));
            return;
        }
        items.forEach(function (item) {
            var btn = el('button', 'app-item');
            btn.appendChild(el('span', 'app-icon', '▸'));
            btn.appendChild(el('span', 'app-name', item.name));
            btn.title = item.path;
            btn.addEventListener('click', async function () {
                try {
                    var data = await api('/monitor/api/open-app', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ path: item.path })
                    });
                    toast(data.message);
                } catch (err) {
                    toast('启动失败: ' + err.message);
                }
            });
            list.appendChild(btn);
        });
    }

    async function refreshTab() {
        try {
            if (currentTab === 'processes') {
                var data = await api('/monitor/api/processes?q=' + encodeURIComponent(procQuery));
                renderProcesses(data.items || []);
            } else if (currentTab === 'windows') {
                var data2 = await api('/monitor/api/windows');
                renderWindows(data2.items || []);
            } else {
                var data3 = await api('/monitor/api/apps');
                renderApps(data3.items || []);
            }
        } catch (err) {
            toast('加载失败: ' + err.message);
        }
    }

    refreshStats();
    refreshPills();
    refreshTab();
    setInterval(refreshStats, 3000);
    setInterval(refreshPills, 8000);
    setInterval(function () {
        if (currentTab === 'processes' && !procQuery) { refreshTab(); }
    }, 5000);
})();
