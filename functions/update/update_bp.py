from flask import Blueprint, render_template
import tempfile
import os
import sys
import threading
import time as timeModule
from flask import request, jsonify
from utils import *

try:
    from functions.update import repoUpdate
except ImportError:
    import repoUpdate

update_bp = Blueprint('update', __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/update/static')


@update_bp.route('/update')
def updatePage():
    return render_template('update.html')


@update_bp.route('/update/api/check')
def updateCheckApi():
    """检查更新：GitHub Release 最新版本与本地 VERSION 比较。

    返回 {current, latest, updateAvailable, releaseUrl, assetUrl, error?}。
    """
    result = {'current': VERSION, 'latest': '', 'updateAvailable': False,
              'releaseUrl': f'https://github.com/{repoUpdate.REPO_PATH}/releases/latest',
              'assetUrl': ''}
    try:
        release = repoUpdate.getRelease()
    except Exception as exc:
        result['error'] = f'获取发行版失败: {exc}'
        return jsonify(result), 502
    latest = str(release.get('tag_name') or '')
    result['latest'] = latest
    result['assetUrl'] = repoUpdate.assetDownloadUrl(release)
    if latest:
        result['updateAvailable'] = repoUpdate.compareVersion(latest, VERSION) > 0
    return jsonify(result)


@update_bp.route('/update/api/update', methods=['POST'])
def updateApi():
    updateMethod = request.form.get('updateMethod', 'remote')
    # 根据更新方式选择对应的更新逻辑
    if updateMethod == 'remote':
        # 远程更新：从指定 URL 下载更新包并执行更新
        updateUrl = request.form.get('updateUrl')
        if not updateUrl:
            return jsonify({'status': 'error', 'message': '缺少更新URL'})
        success, message = remoteUpdate(updateUrl)
        if success:
            # 更新成功后，延迟1秒退出当前进程（确保响应已发送）
            import threading, time

            def exitAfterResponse():
                time.sleep(1)
                os._exit(0)

            threading.Thread(target=exitAfterResponse, daemon=True).start()
            return jsonify({'status': 'success', 'message': message})
        else:
            return jsonify({'status': 'error', 'message': message})
    elif updateMethod == 'nodepool':
        # 节点池更新：加速节点逐个下载最新 Release（公网直连不可达时的正路），
        # 下载到 UPDATER_PATH 后走与本地更新相同的替换重启流程
        try:
            nodes = repoUpdate.speedTest()
            if not nodes:
                return jsonify({'status': 'error', 'message': '所有加速节点均不可达'})
            release = repoUpdate.getRelease()
            downloaded = repoUpdate.downloadUpdater(nodes, release, targetPath=UPDATER_PATH)
            if not downloaded:
                return jsonify({'status': 'error', 'message': '所有节点下载失败'})
            Log.i('更新', f'节点池下载完成: {UPDATER_PATH}')
            success, message = startUpdate(UPDATER_PATH, sys.executable, testDownload=not isPackaged())
        except Exception as exc:
            return jsonify({'status': 'error', 'message': f'节点池更新失败: {exc}'})
        if success:
            # 更新成功后，延迟1秒退出当前进程（确保响应已发送）
            import threading, time

            def exitAfterResponse():
                time.sleep(1)
                os._exit(0)

            threading.Thread(target=exitAfterResponse, daemon=True).start()
            return jsonify({'status': 'success', 'message': message})
        else:
            return jsonify({'status': 'error', 'message': message})
    elif updateMethod == 'local':
        # 本地更新：使用本地上传的更新包执行更新
        updaterFileObject = request.files.get('file')
        if not updaterFileObject:
            return jsonify({'status': 'error', 'message': '未收到更新文件'})
        success, message = localUpdate(updaterFileObject)
        if success:
            # 更新成功后，延迟1秒退出当前进程（确保响应已发送）
            import threading, time

            def exitAfterResponse():
                time.sleep(1)
                os._exit(0)

            threading.Thread(target=exitAfterResponse, daemon=True).start()
            return jsonify({'status': 'success', 'message': message})
        else:
            return jsonify({'status': 'error', 'message': message})
    else:
        return jsonify({'status': 'error', 'message': '未知的更新方式: ' + updateMethod})