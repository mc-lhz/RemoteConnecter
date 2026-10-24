(function () {
    'use strict';

    var INBOX_KEY = 'rc-files-inbox';
    var state = {
        path: '',
        items: [],
        selected: new Map(),
        showHidden: false,
        filter: ''
    };
    var grid = document.getElementById('grid');
    var pathInput = document.getElementById('path-input');
    var ctxMenu = document.getElementById('ctx-menu');
    var modalRoot = document.getElementById('modal-root');
    var toastTimer = 0;
    var marqueeState = { active: false, moved: false, additive: false, sx: 0, sy: 0, el: null, base: null };
    var longPress = { timer: 0, node: null, sx: 0, sy: 0 };
    var lastPointerWasTouch = false;
    var suppressClickUntil = 0;

    function $(id) { return document.getElementById(id); }

    function toast(text) {
        var el = $('toast');
        el.textContent = text;
        el.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { el.hidden = true; }, 2600);
    }

    async function api(url, options) {
        var response = await fetch(url, options);
        var data = null;
        try { data = await response.json(); } catch (e) { data = null; }
        if (!response.ok) {
            throw new Error((data && data.error) || ('HTTP ' + response.status));
        }
        return data;
    }

    function apiPost(url, body) {
        return api(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {})
        });
    }

    function formatBytes(num) {
        var value = Number(num) || 0;
        var units = ['B', 'KB', 'MB', 'GB', 'TB'];
        var i = 0;
        while (value >= 1024 && i < units.length - 1) { value /= 1024; i += 1; }
        return (i === 0 ? Math.round(value) : value.toFixed(1)) + ' ' + units[i];
    }

    function iconFor(item) {
        if (item.type === 'dir') { return '📁'; }
        if (['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.ico'].indexOf(item.ext) >= 0) { return '🖼'; }
        if (['.zip', '.rar', '.7z', '.gz'].indexOf(item.ext) >= 0) { return '🗜'; }
        if (['.mp3', '.wav', '.flac', '.mp4', '.mkv', '.avi'].indexOf(item.ext) >= 0) { return '🎬'; }
        if (['.txt', '.md', '.log', '.ini', '.cfg'].indexOf(item.ext) >= 0) { return '📄'; }
        if (['.py', '.js', '.json', '.html', '.css', '.java', '.c', '.cpp'].indexOf(item.ext) >= 0) { return '📜'; }
        return '📄';
    }

    function visibleItems() {
        var query = state.filter.toLowerCase();
        return state.items.filter(function (item) {
            if (!query) { return true; }
            return item.name.toLowerCase().indexOf(query) >= 0;
        });
    }

    function selectedPaths() {
        return Array.from(state.selected.values()).map(function (item) { return item.path; });
    }

    function selectionSize() {
        var total = 0;
        state.selected.forEach(function (item) { total += item.size || 0; });
        return total;
    }

    function updateStatusbar() {
        var shown = visibleItems();
        $('stat-left').textContent = shown.length + ' 个项目';
        var batch = $('batch-actions');
        if (state.selected.size > 0) {
            batch.hidden = false;
            $('stat-sel').textContent = '已选 ' + state.selected.size + ' 项 (' + formatBytes(selectionSize()) + ')';
        } else {
            batch.hidden = true;
        }
        $('btn-ai').disabled = state.selected.size === 0;
    }

    function render() {
        var items = visibleItems();
        grid.textContent = '';
        $('empty').hidden = items.length > 0;
        items.forEach(function (item) {
            var cell = document.createElement('div');
            cell.className = 'item' + (item.hidden ? ' hidden-item' : '') +
                (state.selected.has(item.path) ? ' selected' : '');
            cell.dataset.path = item.path;
            var thumb = document.createElement('div');
            thumb.className = 'thumb';
            if (['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.ico'].indexOf(item.ext) >= 0 && item.type === 'file') {
                var img = document.createElement('img');
                img.className = 'thumb';
                img.loading = 'lazy';
                img.src = '/files/api/thumb?path=' + encodeURIComponent(item.path);
                img.onerror = function () {
                    img.remove();
                    thumb.textContent = iconFor(item);
                };
                thumb.appendChild(img);
            } else {
                thumb.textContent = iconFor(item);
            }
            cell.appendChild(thumb);
            cell.appendChild(Object.assign(document.createElement('div'), {
                className: 'label',
                textContent: item.name,
                title: item.name + '\n' + (item.type === 'dir' ? '文件夹' : formatBytes(item.size))
            }));
            cell.addEventListener('click', function (event) {
                if (Date.now() < suppressClickUntil) { return; }
                onItemClick(event, item);
            });
            cell.addEventListener('contextmenu', function (event) {
                event.preventDefault();
                if (lastPointerWasTouch) { return; }
                if (!state.selected.has(item.path)) {
                    state.selected.clear();
                    state.selected.set(item.path, item);
                    render();
                }
                openContextMenu(event.clientX, event.clientY);
            });
            cell.addEventListener('dblclick', function () {
                if (Date.now() < suppressClickUntil) { return; }
                onItemOpen(item);
            });
            cell.__item = item;
            grid.appendChild(cell);
        });
        pathInput.value = state.path;
        updateStatusbar();
    }

    function startMarquee(event) {
        marqueeState.active = true;
        marqueeState.moved = false;
        marqueeState.additive = event.ctrlKey || event.metaKey;
        marqueeState.sx = event.clientX;
        marqueeState.sy = event.clientY;
        marqueeState.base = marqueeState.additive ? new Map(state.selected) : new Map();
        var el = document.createElement('div');
        el.className = 'marquee';
        el.style.left = event.clientX + 'px';
        el.style.top = event.clientY + 'px';
        document.body.appendChild(el);
        marqueeState.el = el;
        document.body.classList.add('no-select');
        if (!marqueeState.additive && state.selected.size > 0) {
            state.selected.clear();
            render();
        }
    }

    function updateMarquee(event) {
        if (!marqueeState.active) { return; }
        var dx = event.clientX - marqueeState.sx;
        var dy = event.clientY - marqueeState.sy;
        if (!marqueeState.moved && Math.abs(dx) + Math.abs(dy) > 4) { marqueeState.moved = true; }
        if (!marqueeState.moved) { return; }
        var x1 = Math.min(event.clientX, marqueeState.sx);
        var y1 = Math.min(event.clientY, marqueeState.sy);
        var x2 = Math.max(event.clientX, marqueeState.sx);
        var y2 = Math.max(event.clientY, marqueeState.sy);
        var el = marqueeState.el;
        el.style.left = x1 + 'px';
        el.style.top = y1 + 'px';
        el.style.width = (x2 - x1) + 'px';
        el.style.height = (y2 - y1) + 'px';
        var next = new Map(marqueeState.base);
        var cells = grid.querySelectorAll('.item');
        for (var i = 0; i < cells.length; i++) {
            var rect = cells[i].getBoundingClientRect();
            var hit = !(rect.right < x1 || rect.left > x2 || rect.bottom < y1 || rect.top > y2);
            if (hit && cells[i].__item) { next.set(cells[i].__item.path, cells[i].__item); }
        }
        var changed = next.size !== state.selected.size;
        if (!changed) {
            next.forEach(function (value, key) { if (!state.selected.has(key)) { changed = true; } });
        }
        if (changed) {
            state.selected = next;
            render();
        }
    }

    function endMarquee() {
        if (!marqueeState.active) { return; }
        marqueeState.active = false;
        if (marqueeState.el && marqueeState.el.parentNode) {
            marqueeState.el.parentNode.removeChild(marqueeState.el);
        }
        marqueeState.el = null;
        document.body.classList.remove('no-select');
        if (!marqueeState.moved && !marqueeState.additive && state.selected.size > 0) {
            state.selected.clear();
            render();
        }
    }

    grid.addEventListener('mousedown', function (event) {
        if (event.button !== 0) { return; }
        if (event.target.closest('.item')) { return; }
        event.preventDefault();
        startMarquee(event);
    });
    window.addEventListener('mousemove', updateMarquee);
    window.addEventListener('mouseup', endMarquee);

    function cancelLongPress() {
        if (longPress.timer) {
            clearTimeout(longPress.timer);
            longPress.timer = 0;
        }
        longPress.node = null;
    }

    grid.addEventListener('pointerdown', function (event) {
        lastPointerWasTouch = event.pointerType === 'touch';
        if (!lastPointerWasTouch) { return; }
        var node = event.target.closest('.item');
        if (!node) { return; }
        longPress.sx = event.clientX;
        longPress.sy = event.clientY;
        longPress.node = node;
        longPress.timer = setTimeout(function () {
            longPress.timer = 0;
            var bound = node.__item;
            if (!bound) { return; }
            if (state.selected.has(bound.path)) { state.selected.delete(bound.path); }
            else { state.selected.set(bound.path, bound); }
            suppressClickUntil = Date.now() + 700;
            render();
        }, 500);
    });
    grid.addEventListener('pointermove', function (event) {
        if (!longPress.timer) { return; }
        if (Math.abs(event.clientX - longPress.sx) + Math.abs(event.clientY - longPress.sy) > 8) {
            cancelLongPress();
        }
    });
    grid.addEventListener('pointerup', cancelLongPress);
    grid.addEventListener('pointercancel', cancelLongPress);

    function onItemClick(event, item) {
        if (event.ctrlKey || event.metaKey) {
            if (state.selected.has(item.path)) { state.selected.delete(item.path); }
            else { state.selected.set(item.path, item); }
        } else if (event.shiftKey && state.selected.size > 0) {
            var items = visibleItems();
            var lastPath = Array.from(state.selected.keys()).pop();
            var startIdx = items.findIndex(function (x) { return x.path === lastPath; });
            var endIdx = items.findIndex(function (x) { return x.path === item.path; });
            if (startIdx >= 0 && endIdx >= 0) {
                state.selected.clear();
                items.slice(Math.min(startIdx, endIdx), Math.max(startIdx, endIdx) + 1)
                    .forEach(function (x) { state.selected.set(x.path, x); });
            }
        } else {
            state.selected.clear();
            state.selected.set(item.path, item);
        }
        render();
    }

    function onItemOpen(item) {
        if (item.type === 'dir') {
            navigate(item.path);
        } else {
            openPreview(item);
        }
    }

    async function navigate(path) {
        try {
            var data = await api('/files/api/list?path=' + encodeURIComponent(path || '') +
                '&showHidden=' + (state.showHidden ? '1' : '0'));
            state.path = data.path;
            state.items = data.items;
            state.selected.clear();
            render();
            try { localStorage.setItem('rc-files-last', state.path); } catch (e) {}
        } catch (err) {
            toast('打开失败: ' + err.message);
        }
    }

    function closeModal() {
        modalRoot.hidden = true;
        modalRoot.textContent = '';
    }

    function openModal(title, bodyBuilder, actions) {
        modalRoot.textContent = '';
        modalRoot.hidden = false;
        var modal = document.createElement('div');
        modal.className = 'modal';
        modal.appendChild(Object.assign(document.createElement('h3'), { textContent: title }));
        var body = document.createElement('div');
        body.className = 'modal-body';
        modal.appendChild(body);
        var actionsRow = document.createElement('div');
        actionsRow.className = 'modal-actions';
        (actions || []).forEach(function (spec) {
            var btn = document.createElement('button');
            btn.textContent = spec.label;
            if (spec.primary) { btn.className = 'primary'; }
            btn.addEventListener('click', function () { spec.onClick(body); });
            actionsRow.appendChild(btn);
        });
        modal.appendChild(actionsRow);
        modalRoot.appendChild(modal);
        modalRoot.onclick = function (event) { if (event.target === modalRoot) { closeModal(); } };
        if (bodyBuilder) { bodyBuilder(body); }
        return body;
    }

    function openPreview(item) {
        if (['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.ico'].indexOf(item.ext) >= 0) {
            openModal(item.name, function (body) {
                var img = document.createElement('img');
                img.src = '/files/api/raw?path=' + encodeURIComponent(item.path);
                body.appendChild(img);
            }, [{ label: '关闭', onClick: closeModal }]);
            return;
        }
        if (['.txt', '.md', '.py', '.js', '.css', '.html', '.json', '.csv', '.log', '.xml', '.yaml', '.yml',
             '.ini', '.cfg', '.bat', '.ps1', '.sh', '.sql', '.java', '.c', '.cpp', '.h'].indexOf(item.ext) >= 0) {
            openModal(item.name, function (body) {
                body.textContent = '加载中...';
                api('/files/api/text?path=' + encodeURIComponent(item.path)).then(function (data) {
                    body.textContent = '';
                    var pre = document.createElement('pre');
                    pre.textContent = data.text + (data.truncated ? '\n\n... (已截断)' : '');
                    body.appendChild(pre);
                }).catch(function (err) {
                    body.textContent = '预览失败: ' + err.message;
                });
            }, [{ label: '关闭', onClick: closeModal }]);
            return;
        }
        openModal(item.name, function (body) {
            body.textContent = '该类型暂不支持预览，可双击用系统默认程序打开。';
        }, [{ label: '关闭', onClick: closeModal }]);
    }

    function promptModal(title, placeholder, initial, onSubmit) {
        var body = openModal(title, function (bodyEl) {
            var input = document.createElement('input');
            input.type = 'text';
            input.placeholder = placeholder || '';
            input.value = initial || '';
            input.id = 'modal-input';
            bodyEl.appendChild(input);
            input.addEventListener('keydown', function (event) {
                if (event.key === 'Enter') {
                    var value = input.value.trim();
                    if (value) { onSubmit(value); }
                }
            });
            setTimeout(function () { input.focus(); input.select(); }, 30);
        }, [
            { label: '取消', onClick: closeModal },
            {
                label: '确定', primary: true, onClick: function () {
                    var value = $('modal-input').value.trim();
                    if (value) { onSubmit(value); }
                }
            }
        ]);
        return body;
    }

    var CONTEXT_ITEMS = [
        { label: '预览', when: singleFile, run: function () { openPreview(singleItem()); } },
        { label: '用记事本打开', when: singleFile, run: notepadOpen },
        { label: '问 AI', when: anySelection, run: askAi },
        { label: '在终端中打开', when: anySelection, run: terminalOpen },
        { separator: true },
        { label: '下载', when: anySelection, run: downloadSelection },
        { label: '压缩', when: anySelection, run: compressSelection },
        { separator: true },
        { label: '复制', when: anySelection, run: function () { copyMoveSelection(false); } },
        { label: '移动', when: anySelection, run: function () { copyMoveSelection(true); } },
        { label: '复制路径', when: anySelection, run: copyPaths },
        { separator: true },
        { label: '重命名', when: singleAny, run: renameItem },
        { label: '属性', when: anySelection, run: showProperties },
        { label: '删除', when: anySelection, danger: true, run: deleteSelection }
    ];

    function singleItem() { return state.selected.values().next().value; }
    function singleFile() { return state.selected.size === 1 && singleItem().type === 'file'; }
    function singleAny() { return state.selected.size === 1; }
    function anySelection() { return state.selected.size > 0; }

    function openContextMenu(x, y) {
        ctxMenu.textContent = '';
        var shown = 0;
        CONTEXT_ITEMS.forEach(function (spec) {
            if (spec.separator) {
                ctxMenu.appendChild(Object.assign(document.createElement('div'), { className: 'ctx-sep' }));
                return;
            }
            if (spec.when && !spec.when()) { return; }
            var btn = document.createElement('button');
            btn.className = 'ctx-item';
            btn.textContent = spec.label;
            btn.addEventListener('click', function () {
                closeContextMenu();
                spec.run();
            });
            ctxMenu.appendChild(btn);
            shown += 1;
        });
        if (!shown) { return; }
        ctxMenu.hidden = false;
        var rect = ctxMenu.getBoundingClientRect();
        ctxMenu.style.left = Math.min(x, window.innerWidth - rect.width - 8) + 'px';
        ctxMenu.style.top = Math.min(y, window.innerHeight - rect.height - 8) + 'px';
    }

    function closeContextMenu() { ctxMenu.hidden = true; }
    document.addEventListener('click', function (event) {
        if (!ctxMenu.contains(event.target)) { closeContextMenu(); }
    });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') { closeContextMenu(); closeModal(); }
    });

    async function notepadOpen() {
        try {
            var data = await apiPost('/files/api/notepad', { path: singleItem().path });
            toast(data.message);
        } catch (err) { toast('失败: ' + err.message); }
    }

    async function terminalOpen() {
        try {
            var data = await apiPost('/files/api/terminal', { path: singleItem().path });
            window.open(data.url, '_blank');
        } catch (err) { toast('失败: ' + err.message); }
    }

    async function askAi() {
        var paths = selectedPaths();
        promptModal('问 AI', '输入你的问题（将连同所选文件路径一起复制）', '', function (question) {
            var prompt = '文件:\n' + paths.join('\n') + '\n\n问题: ' + question;
            navigator.clipboard.writeText(prompt).then(function () {
                closeModal();
                toast('提问模板已复制到剪贴板，请粘贴到 AI 对话');
            }, function () {
                closeModal();
                openModal('提问模板', function (body) {
                    var pre = document.createElement('pre');
                    pre.textContent = prompt;
                    body.appendChild(pre);
                }, [{ label: '关闭', onClick: closeModal }]);
            });
        });
    }

    function downloadSelection() {
        var paths = selectedPaths();
        if (!paths.length) { return; }
        var url = '/files/api/download?paths=' + encodeURIComponent(paths.join('|'));
        var link = document.createElement('a');
        link.href = url;
        link.click();
        toast('开始下载');
    }

    async function compressSelection() {
        var paths = selectedPaths();
        var first = singleItem();
        promptModal('压缩为 ZIP', '压缩包名称', (first ? first.name : 'archive'), async function (name) {
            try {
                var data = await apiPost('/files/api/compress', { paths: paths, destName: name });
                closeModal();
                toast('已压缩: ' + data.path + ' (' + formatBytes(data.size) + ')');
                navigate(state.path);
            } catch (err) { toast('压缩失败: ' + err.message); }
        });
    }

    async function copyMoveSelection(isMove) {
        var paths = selectedPaths();
        var verb = isMove ? '移动' : '复制';
        promptModal(verb + '到目录', '目标目录完整路径', state.path, async function (destDir) {
            try {
                var data = await apiPost(isMove ? '/files/api/move' : '/files/api/copy', { paths: paths, destDir: destDir });
                closeModal();
                if (data.failed && data.failed.length) {
                    toast(verb + '部分失败: ' + data.failed[0].error);
                } else {
                    toast(verb + '完成 ' + data.moved.length + ' 项');
                }
                navigate(state.path);
            } catch (err) { toast(verb + '失败: ' + err.message); }
        });
    }

    async function copyPaths() {
        var text = selectedPaths().join('\n');
        try {
            await navigator.clipboard.writeText(text);
            toast('路径已复制');
        } catch (err) {
            openModal('路径', function (body) {
                var pre = document.createElement('pre');
                pre.textContent = text;
                body.appendChild(pre);
            }, [{ label: '关闭', onClick: closeModal }]);
        }
    }

    function renameItem() {
        var item = singleItem();
        promptModal('重命名', '新名称', item.name, async function (newName) {
            try {
                await apiPost('/files/api/rename', { path: item.path, newName: newName });
                closeModal();
                toast('已重命名');
                navigate(state.path);
            } catch (err) { toast('重命名失败: ' + err.message); }
        });
    }

    function showProperties() {
        var item = singleItem();
        api('/files/api/properties?path=' + encodeURIComponent(item.path)).then(function (props) {
            var lines = ['路径: ' + props.path, '类型: ' + (props.type === 'dir' ? '文件夹' : '文件')];
            if (props.type === 'dir') { lines.push('包含: ' + props.children + ' 项'); }
            lines.push('大小: ' + formatBytes(props.size));
            lines.push('修改时间: ' + new Date(props.mtime).toLocaleString());
            lines.push('创建时间: ' + new Date(props.ctime).toLocaleString());
            lines.push('属性: ' + [props.hidden ? '隐藏' : null, props.readonly ? '只读' : null].filter(Boolean).join(', ') || '常规');
            openModal('属性 — ' + props.name, function (body) {
                var pre = document.createElement('pre');
                pre.textContent = lines.join('\n');
                body.appendChild(pre);
            }, [{ label: '关闭', onClick: closeModal }]);
        }).catch(function (err) { toast('失败: ' + err.message); });
    }

    function deleteSelection() {
        var paths = selectedPaths();
        if (!confirm('确认删除选中的 ' + paths.length + ' 项？此操作不可恢复。')) { return; }
        apiPost('/files/api/delete', { paths: paths }).then(function (data) {
            state.selected.clear();
            if (data.failed && data.failed.length) {
                toast('删除部分失败: ' + data.failed[0].error);
            } else {
                toast('已删除 ' + data.deleted.length + ' 项');
            }
            navigate(state.path);
        }).catch(function (err) { toast('删除失败: ' + err.message); });
    }

    function batchRun(op) {
        if (op === 'clear') { state.selected.clear(); render(); return; }
        if (op === 'download') { downloadSelection(); return; }
        if (op === 'compress') { compressSelection(); return; }
        if (op === 'copy') { copyMoveSelection(false); return; }
        if (op === 'move') { copyMoveSelection(true); return; }
        if (op === 'delete') { deleteSelection(); return; }
    }

    document.querySelectorAll('[data-batch]').forEach(function (btn) {
        btn.addEventListener('click', function () { batchRun(btn.getAttribute('data-batch')); });
    });

    $('btn-newdir').addEventListener('click', function () {
        promptModal('新建文件夹', '文件夹名称', '新建文件夹', async function (name) {
            try {
                await apiPost('/files/api/mkdir', { path: state.path, name: name });
                closeModal();
                toast('已创建 ' + name);
                navigate(state.path);
            } catch (err) { toast('创建失败: ' + err.message); }
        });
    });

    $('btn-upload').addEventListener('click', function () {
        $('file-input').value = '';
        $('file-input').click();
    });

    $('file-input').addEventListener('change', async function () {
        var files = Array.from(this.files || []);
        if (!files.length) { return; }
        var form = new FormData();
        form.append('path', state.path);
        files.forEach(function (file) { form.append('file', file); });
        try {
            var data = await api('/files/api/upload', { method: 'POST', body: form });
            toast(data.failed && data.failed.length
                ? '上传部分失败: ' + data.failed[0].error
                : '已上传 ' + data.saved.length + ' 个文件');
            navigate(state.path);
        } catch (err) { toast('上传失败: ' + err.message); }
    });

    $('btn-ai').addEventListener('click', askAi);

    $('show-hidden').addEventListener('change', function () {
        state.showHidden = this.checked;
        navigate(state.path);
    });

    $('filter-input').addEventListener('input', function () {
        state.filter = this.value.trim();
        render();
    });

    $('btn-up').addEventListener('click', function () {
        if (state.path) { navigate(osUp(state.path)); }
    });

    $('btn-refresh').addEventListener('click', function () { navigate(state.path); });

    pathInput.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') { navigate(pathInput.value.trim()); }
    });

    function osUp(path) {
        var normalized = path.replace(/[\\/]+$/, '');
        var idx = Math.max(normalized.lastIndexOf('\\'), normalized.lastIndexOf('/'));
        if (idx < 0) { return normalized; }
        var parent = normalized.slice(0, idx + 1);
        if (/^[a-zA-Z]:\\?$/.test(parent) || parent.length <= 3) { return parent; }
        return parent.replace(/[\\/]+$/, '');
    }

    function buildQuick(items) {
        var box = $('quick-list');
        box.textContent = '';
        items.forEach(function (entry) {
            var btn = document.createElement('button');
            btn.className = 'side-item';
            btn.textContent = '🏠 ' + entry.label;
            btn.title = entry.path;
            btn.addEventListener('click', function () { navigate(entry.path); });
            box.appendChild(btn);
        });
    }

    function buildDrives(drives) {
        var box = $('drive-list');
        box.textContent = '';
        drives.forEach(function (drive) {
            var btn = document.createElement('button');
            btn.className = 'side-item';
            btn.textContent = '💽 ' + drive;
            btn.addEventListener('click', function () { navigate(drive); });
            box.appendChild(btn);
        });
    }

    var inboxBtn = document.querySelector('[data-nav="inbox"]');
    inboxBtn.addEventListener('click', function () {
        var inbox = localStorage.getItem(INBOX_KEY);
        if (inbox) { navigate(inbox); return; }
        api('/files/api/quick').then(function (data) {
            var docs = (data.items || []).find(function (x) { return x.label === '文档'; });
            var target = docs ? docs.path + '\\RemoteConnecter收件箱' : 'C:\\ProgramData\\RemoteConnecter\\收件箱';
            apiPost('/files/api/mkdir', { path: docs ? docs.path : 'C:\\ProgramData\\RemoteConnecter', name: docs ? 'RemoteConnecter收件箱' : '收件箱' })
                .catch(function () {}).then(function () {
                    localStorage.setItem(INBOX_KEY, target);
                    navigate(target);
                });
        });
    });

    (async function init() {
        var drives = await api('/files/api/drives');
        buildDrives(drives.drives || []);
        var quick = await api('/files/api/quick');
        buildQuick(quick.items || []);
        var last = '';
        try { last = localStorage.getItem('rc-files-last') || ''; } catch (e) {}
        navigate(last || (drives.drives || [])[0] || '');
    })();
})();
