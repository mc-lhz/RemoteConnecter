# -*- coding: utf-8 -*-
"""文件管理器 — 网格浏览 / 批量操作 / 压缩 / 预览 / 终端联动"""

import ctypes
import io
import mimetypes
import os
import shutil
import string
import subprocess
import tempfile
import zipfile

from flask import Blueprint, jsonify, render_template, request, send_file

import Logcat

Log = Logcat.Logcat()
from utils import resourcePath

pluginID = 'files'
files_bp = Blueprint(
    f'{pluginID}_bp',
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path=f'/{pluginID}/static',
)

file_attributes = ctypes.windll.kernel32.GetFileAttributesW
INVALID_ATTRIBUTES = 0xFFFFFFFF
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.ico'}
TEXT_EXTS = {'.txt', '.md', '.py', '.js', '.css', '.html', '.json', '.csv', '.log',
             '.xml', '.yaml', '.yml', '.ini', '.cfg', '.bat', '.ps1', '.sh', '.sql', '.java', '.c', '.cpp', '.h'}
PREVIEW_MAX_TEXT = 64 * 1024


def isHiddenPath(path):
    attrs = file_attributes(ctypes.c_wchar_p(path))
    if attrs == INVALID_ATTRIBUTES:
        return False
    return bool(attrs & 0x2)


def safeListDir(path):
    try:
        return os.listdir(path)
    except (PermissionError, OSError):
        return []


def itemInfo(path, name):
    full = os.path.join(path, name)
    try:
        stat = os.stat(full)
    except (OSError, PermissionError):
        return None
    isDir = os.path.isdir(full)
    return {
        'name': name,
        'path': full,
        'type': 'dir' if isDir else 'file',
        'size': 0 if isDir else stat.st_size,
        'mtime': int(stat.st_mtime * 1000),
        'hidden': isHiddenPath(full),
        'ext': '' if isDir else os.path.splitext(name)[1].lower(),
    }


def resolveExisting(path):
    path = (path or '').strip()
    if not path:
        return None
    path = os.path.abspath(path)
    return path if os.path.exists(path) else None


def uniqueDestination(directory, name):
    target = os.path.join(directory, name)
    if not os.path.exists(target):
        return target
    stem, ext = os.path.splitext(name)
    for i in range(1, 1000):
        candidate = os.path.join(directory, f'{stem} ({i}){ext}')
        if not os.path.exists(candidate):
            return candidate
    raise FileExistsError(target)


@files_bp.route(f'/{pluginID}')
def filesPage():
    return render_template('files.html', pluginID=pluginID)


@files_bp.route(f'/{pluginID}/api/drives')
def apiDrives():
    drives = []
    for letter in string.ascii_uppercase:
        root = f'{letter}:\\'
        if os.path.exists(root):
            drives.append(root)
    return jsonify({'drives': drives})


@files_bp.route(f'/{pluginID}/api/quick')
def apiQuick():
    home = os.path.expanduser('~')
    entries = []
    for label, path in (
        ('主目录', home),
        ('桌面', os.path.join(home, 'Desktop')),
        ('下载', os.path.join(home, 'Downloads')),
        ('文档', os.path.join(home, 'Documents')),
        ('图片', os.path.join(home, 'Pictures')),
    ):
        if os.path.isdir(path):
            entries.append({'label': label, 'path': path})
    return jsonify({'items': entries})


@files_bp.route(f'/{pluginID}/api/list')
def apiList():
    path = resolveExisting(request.args.get('path') or os.path.expanduser('~'))
    if path is None:
        return jsonify({'error': 'path not found'}), 404
    if os.path.isfile(path):
        path = os.path.dirname(path)
    showHidden = request.args.get('showHidden') == '1'
    items = []
    for name in safeListDir(path):
        info = itemInfo(path, name)
        if info and (showHidden or not info['hidden']):
            items.append(info)
    items.sort(key=lambda x: (x['type'] != 'dir', x['name'].lower()))
    parent = os.path.dirname(path) if len(os.path.splitdrive(path)[1]) > 1 else None
    return jsonify({'path': path, 'parent': parent, 'items': items})


@files_bp.route(f'/{pluginID}/api/mkdir', methods=['POST'])
def apiMkdir():
    body = request.get_json(silent=True) or {}
    directory = resolveExisting(body.get('path'))
    name = str(body.get('name') or '').strip()
    if directory is None or not name or any(ch in name for ch in '\\/:*?"<>|'):
        return jsonify({'error': '参数无效'}), 400
    target = uniqueDestination(directory, name)
    os.mkdir(target)
    return jsonify({'ok': True, 'path': target})


@files_bp.route(f'/{pluginID}/api/rename', methods=['POST'])
def apiRename():
    body = request.get_json(silent=True) or {}
    path = resolveExisting(body.get('path'))
    newName = str(body.get('newName') or '').strip()
    if path is None or not newName or any(ch in newName for ch in '\\/:*?"<>|'):
        return jsonify({'error': '参数无效'}), 400
    target = uniqueDestination(os.path.dirname(path), newName)
    os.rename(path, target)
    return jsonify({'ok': True, 'path': target})


@files_bp.route(f'/{pluginID}/api/delete', methods=['POST'])
def apiDelete():
    body = request.get_json(silent=True) or {}
    paths = body.get('paths') or []
    deleted, failed = [], []
    for raw in paths:
        path = resolveExisting(raw)
        if path is None:
            failed.append({'path': raw, 'error': '不存在'})
            continue
        drive = os.path.splitdrive(path)[0] + os.sep
        if os.path.normcase(path) in (os.path.normcase(drive), os.path.normcase(os.path.expanduser('~'))):
            failed.append({'path': path, 'error': '拒绝删除驱动器根目录或主目录'})
            continue
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            deleted.append(path)
        except (OSError, PermissionError) as exc:
            failed.append({'path': path, 'error': str(exc)})
    return jsonify({'ok': not failed, 'deleted': deleted, 'failed': failed})


def _expandDirs(paths):
    result = []
    for path in paths:
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                for name in dirs:
                    result.append((os.path.join(root, name), None))
                for name in files:
                    full = os.path.join(root, name)
                    arc = os.path.relpath(full, os.path.dirname(path))
                    result.append((full, arc))
        elif os.path.isfile(path):
            result.append((path, os.path.basename(path)))
    return result


@files_bp.route(f'/{pluginID}/api/compress', methods=['POST'])
def apiCompress():
    body = request.get_json(silent=True) or {}
    paths = [resolveExisting(p) for p in (body.get('paths') or [])]
    paths = [p for p in paths if p]
    if not paths:
        return jsonify({'error': '没有可压缩的项'}), 400
    destName = str(body.get('destName') or '').strip() or os.path.basename(paths[0])
    destName = os.path.splitext(destName)[0] + '.zip'
    dest = uniqueDestination(os.path.dirname(paths[0]), destName)
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as zf:
        for full, arc in _expandDirs(paths):
            try:
                zf.write(full, arc or os.path.basename(full))
            except (OSError, PermissionError) as exc:
                Log.w('files', f'compress skip {full}: {exc}')
    return jsonify({'ok': True, 'path': dest, 'size': os.path.getsize(dest)})


@files_bp.route(f'/{pluginID}/api/copy', methods=['POST'])
def apiCopy():
    return _copyOrMove(request, move=False)


@files_bp.route(f'/{pluginID}/api/move', methods=['POST'])
def apiMove():
    return _copyOrMove(request, move=True)


def _copyOrMove(req, move):
    body = req.get_json(silent=True) or {}
    destDir = resolveExisting(body.get('destDir'))
    paths = [resolveExisting(p) for p in (body.get('paths') or [])]
    paths = [p for p in paths if p]
    overwrite = bool(body.get('overwrite'))
    if destDir is None or not os.path.isdir(destDir) or not paths:
        return jsonify({'error': '参数无效'}), 400
    moved, failed = [], []
    for path in paths:
        target = os.path.join(destDir, os.path.basename(path))
        if os.path.abspath(target) == os.path.abspath(path):
            failed.append({'path': path, 'error': '源与目标相同'})
            continue
        try:
            if not overwrite and os.path.exists(target):
                target = uniqueDestination(destDir, os.path.basename(path))
            if move:
                shutil.move(path, target)
            else:
                if os.path.isdir(path):
                    shutil.copytree(path, target, dirs_exist_ok=overwrite)
                else:
                    shutil.copy2(path, target)
            moved.append(target)
        except (OSError, PermissionError, shutil.Error) as exc:
            failed.append({'path': path, 'error': str(exc)})
    return jsonify({'ok': not failed, 'moved': moved, 'failed': failed})


@files_bp.route(f'/{pluginID}/api/download')
def apiDownload():
    raws = (request.args.get('paths') or '').split('|')
    paths = [resolveExisting(p) for p in raws if p.strip()]
    paths = [p for p in paths if p]
    if not paths:
        return jsonify({'error': '没有可下载的项'}), 400
    if len(paths) == 1 and os.path.isfile(paths[0]):
        path = paths[0]
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))
    tmp = os.path.join(tempfile.gettempdir(), f'rc-files-dl-{os.getpid()}-{os.urandom(4).hex()}.zip')
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zf:
        for full, arc in _expandDirs(paths):
            try:
                zf.write(full, arc or os.path.basename(full))
            except (OSError, PermissionError) as exc:
                Log.w('files', f'download skip {full}: {exc}')
    return send_file(tmp, as_attachment=True, download_name='files.zip')


@files_bp.route(f'/{pluginID}/api/upload', methods=['POST'])
def apiUpload():
    destDir = resolveExisting(request.form.get('path'))
    overwrite = request.form.get('overwrite') == 'true'
    uploads = request.files.getlist('file')
    if destDir is None or not os.path.isdir(destDir) or not uploads:
        return jsonify({'error': '参数无效'}), 400
    saved, failed = [], []
    for storage in uploads:
        name = os.path.basename(storage.filename or '')
        if not name:
            continue
        target = os.path.join(destDir, name)
        if not overwrite and os.path.exists(target):
            try:
                target = uniqueDestination(destDir, name)
            except FileExistsError:
                failed.append({'name': name, 'error': '目标已存在'})
                continue
        try:
            storage.save(target)
            saved.append(target)
        except OSError as exc:
            failed.append({'name': name, 'error': str(exc)})
    return jsonify({'ok': not failed, 'saved': saved, 'failed': failed})


@files_bp.route(f'/{pluginID}/api/raw')
def apiRaw():
    path = resolveExisting(request.args.get('path'))
    if path is None or not os.path.isfile(path):
        return jsonify({'error': 'file not found'}), 404
    mimeType = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    response = send_file(path, mimetype=mimeType, as_attachment=False, conditional=True)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    return response


@files_bp.route(f'/{pluginID}/api/text')
def apiText():
    path = resolveExisting(request.args.get('path'))
    if path is None or not os.path.isfile(path):
        return jsonify({'error': 'file not found'}), 404
    ext = os.path.splitext(path)[1].lower()
    if ext not in TEXT_EXTS and not (mimetypes.guess_type(path)[0] or '').startswith('text/'):
        return jsonify({'error': 'not a text file'}), 415
    with open(path, 'rb') as f:
        data = f.read(PREVIEW_MAX_TEXT)
    for encoding in ('utf-8-sig', 'utf-8', 'gbk'):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            text = None
    if text is None:
        return jsonify({'error': '无法识别的编码'}), 415
    return jsonify({'path': path, 'text': text, 'truncated': os.path.getsize(path) > PREVIEW_MAX_TEXT})


@files_bp.route(f'/{pluginID}/api/thumb')
def apiThumb():
    path = resolveExisting(request.args.get('path'))
    if path is None or not os.path.isfile(path):
        return 'not found', 404
    if os.path.splitext(path)[1].lower() not in IMAGE_EXTS:
        return 'unsupported', 415
    from PIL import Image
    image = Image.open(path)
    image.thumbnail((128, 128))
    buf = io.BytesIO()
    image.convert('RGB').save(buf, 'JPEG', quality=80)
    response = send_file(io.BytesIO(buf.getvalue()), mimetype='image/jpeg', conditional=False)
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response


@files_bp.route(f'/{pluginID}/api/notepad', methods=['POST'])
def apiNotepad():
    body = request.get_json(silent=True) or {}
    path = resolveExisting(body.get('path'))
    if path is None or not os.path.isfile(path):
        return jsonify({'error': 'file not found'}), 404
    subprocess.Popen(['notepad.exe', path])
    return jsonify({'ok': True, 'message': '已在记事本打开'})


@files_bp.route(f'/{pluginID}/api/terminal', methods=['POST'])
def apiTerminal():
    body = request.get_json(silent=True) or {}
    path = resolveExisting(body.get('path'))
    if path is None:
        return jsonify({'error': 'path not found'}), 404
    cwd = path if os.path.isdir(path) else os.path.dirname(path)
    return jsonify({'ok': True, 'cwd': cwd, 'url': '/terminal?cwd=' + request.host_url.rstrip('/') + cwd})


@files_bp.route(f'/{pluginID}/api/properties')
def apiProperties():
    path = resolveExisting(request.args.get('path'))
    if path is None:
        return jsonify({'error': 'path not found'}), 404
    stat = os.stat(path)
    isDir = os.path.isdir(path)
    attrs = file_attributes(ctypes.c_wchar_p(path))
    props = {
        'path': path,
        'name': os.path.basename(path),
        'type': 'dir' if isDir else 'file',
        'size': 0 if isDir else stat.st_size,
        'mtime': int(stat.st_mtime * 1000),
        'ctime': int(stat.st_ctime * 1000),
        'hidden': bool(attrs & 0x2) if attrs != INVALID_ATTRIBUTES else False,
        'readonly': bool(attrs & 0x1) if attrs != INVALID_ATTRIBUTES else False,
    }
    if isDir:
        count = 0
        total = 0
        for root, dirs, files in os.walk(path):
            count += len(dirs) + len(files)
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
        props['children'] = count
        props['size'] = total
    return jsonify(props)
