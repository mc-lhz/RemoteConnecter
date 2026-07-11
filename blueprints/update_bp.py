from flask import Blueprint, render_template
import tempfile
import os
from flask import request, jsonify
from utils import *

update_bp = Blueprint('update', __name__)


@update_bp.route('/update')
def updatePage():
    return render_template('update.html')


@update_bp.route('/api/update', methods=['POST'])
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