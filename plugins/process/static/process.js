// 进程管理前端：列表拉取/过滤/自动刷新 + 终止确认
(function () {
    'use strict';

    var REFRESH_MS = 3000;
    var timer = null;
    var allRows = [];
    var pendingKill = null;

    var dom = {
        filter: document.getElementById('filter'),
        auto: document.getElementById('auto'),
        refresh: document.getElementById('refresh'),
        summary: document.getElementById('summary'),
        rows: document.getElementById('rows'),
        modal: document.getElementById('modal'),
        modalTitle: document.getElementById('modal-title'),
        modalText: document.getElementById('modal-text'),
        modalOk: document.getElementById('modal-ok'),
        modalCancel: document.getElementById('modal-cancel')
    };

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) { node.className = className; }
        if (text !== undefined) { node.textContent = text; }
        return node;
    }

    function load() {
        fetch('/process/api/list', { cache: 'no-store' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                allRows = data.processes || [];
                dom.summary.textContent = '共 ' + (data.total || allRows.length) + ' 个进程'
                    + (data.truncated ? '（仅显示前 ' + allRows.length + '）' : '');
                render();
            })
            .catch(function () {
                dom.summary.textContent = '刷新失败';
            });
    }

    function render() {
        var q = dom.filter.value.trim().toLowerCase();
        var list = allRows;
        if (q) {
            list = allRows.filter(function (p) {
                return p.name.toLowerCase().indexOf(q) >= 0 || String(p.pid) === q;
            });
        }
        dom.rows.innerHTML = '';
        if (!list.length) {
            var tr = el('tr');
            var td = el('td', 'empty', '没有匹配的进程');
            td.colSpan = 7;
            tr.appendChild(td);
            dom.rows.appendChild(tr);
            return;
        }
        list.forEach(function (p) {
            var tr = el('tr');
            if (p.self) { tr.className = 'self'; }

            tr.appendChild(el('td', 'col-pid', String(p.pid)));

            var nameTd = el('td', 'name-cell', p.name);
            nameTd.title = p.name;
            tr.appendChild(nameTd);

            var cpuTd = el('td', 'col-num', p.cpu.toFixed(1) + '%');
            if (p.cpu >= 50) { cpuTd.classList.add('cpu-hot'); }
            else if (p.cpu >= 10) { cpuTd.classList.add('cpu-warm'); }
            tr.appendChild(cpuTd);

            var memTd = el('td', 'col-num', p.mem.toFixed(1) + '%');
            if (p.mem >= 10) { memTd.classList.add('mem-hot'); }
            tr.appendChild(memTd);

            tr.appendChild(el('td', 'col-status', p.status || '-'));
            tr.appendChild(el('td', 'user-cell', p.user || '-'));

            var opTd = el('td', 'col-op');
            var killBtn = el('button', 'kill-btn', '终止');
            killBtn.type = 'button';
            killBtn.title = p.self ? '本程序自身，禁止终止' : '终止该进程';
            if (p.self) { killBtn.disabled = true; }
            killBtn.addEventListener('click', function () { askKill(p); });
            opTd.appendChild(killBtn);
            tr.appendChild(opTd);

            dom.rows.appendChild(tr);
        });
    }

    function askKill(p) {
        pendingKill = p;
        dom.modalTitle.textContent = '终止进程';
        dom.modalText.textContent = '确定终止 ' + p.name + '（PID ' + p.pid + '）吗？未保存的数据将丢失。';
        dom.modal.classList.remove('hidden');
    }

    function closeModal() {
        dom.modal.classList.add('hidden');
        pendingKill = null;
    }

    function doKill() {
        if (!pendingKill) { return; }
        var target = pendingKill;
        dom.modalOk.disabled = true;
        fetch('/process/api/kill', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pid: target.pid, name: target.name })
        })
            .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
            .then(function (result) {
                dom.modalOk.disabled = false;
                closeModal();
                dom.summary.textContent = result.ok
                    ? '已终止 ' + target.name + '（PID ' + target.pid + '）'
                    : '终止失败：' + (result.data.error || '未知错误');
                load();
            })
            .catch(function () {
                dom.modalOk.disabled = false;
                closeModal();
                dom.summary.textContent = '终止请求失败';
            });
    }

    function schedule() {
        if (timer) { clearInterval(timer); }
        if (dom.auto.checked) {
            timer = setInterval(function () {
                if (!document.hidden) { load(); }
            }, REFRESH_MS);
        }
    }

    dom.refresh.addEventListener('click', load);
    dom.filter.addEventListener('input', render);
    dom.auto.addEventListener('change', schedule);
    dom.modalCancel.addEventListener('click', closeModal);
    dom.modalOk.addEventListener('click', doKill);
    dom.modal.addEventListener('click', function (e) {
        if (e.target === dom.modal) { closeModal(); }
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !dom.modal.classList.contains('hidden')) { closeModal(); }
    });

    load();
    schedule();
})();
