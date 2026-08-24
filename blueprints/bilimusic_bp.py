from flask import Blueprint, request, jsonify, render_template
import os
import re
import tempfile
import subprocess
import bilimusic
from pygame import mixer
from utils import resourcePath

bilimusic_bp = Blueprint('bilimusic', __name__)

TEMP_DIR = tempfile.gettempdir()
M4A_FILE_NAME = "RemoteConnecterBiliMusic.m4a"
MP3_FILE_NAME = "RemoteConnecterBiliMusic.mp3"
m4aPath = os.path.join(TEMP_DIR, M4A_FILE_NAME)
mp3Path = os.path.join(TEMP_DIR, MP3_FILE_NAME)
# 优先使用项目目录下的 ffmpeg.exe，找不到则使用系统 PATH 中的 ffmpeg
# 注: 使用精简版 ffmpeg-mini (仅 m4a->mp3), 不含 ffprobe,
#     时长改由 ffmpeg 转码输出解析, 见 parseDuration()。
FFMPEG_PATH = resourcePath('ffmpeg.exe')
if not os.path.exists(FFMPEG_PATH):
    FFMPEG_PATH = 'ffmpeg'

currentBvid = None
isPlaying = False
isPaused = False
isStopped = True


def initMixer():
    if not mixer.get_init():
        mixer.init()


def runFfmpeg(args):
    return subprocess.run(
        [FFMPEG_PATH] + args,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )


def m4aToMp3(inputPath, outputPath):
    # 精简版 ffmpeg-mini 默认输出 mp3 (libmp3lame); 仅做 m4a->mp3。
    # 用 -b:a 320k 固定高码率, 减轻 AAC->MP3 二次有损转码的音质损失
    # (mini 构建未指定 -b:a 时 LAME 默认 128k, 对高码率原档损失明显)。
    result = runFfmpeg(['-y', '-i', inputPath, '-vn', '-b:a', '320k', outputPath])
    success = result.returncode == 0
    errMsg = result.stderr.decode('utf-8', errors='ignore')
    duration = parseDuration(errMsg)
    return success, errMsg, duration


def parseDuration(ffmpegOutput):
    """
    从 ffmpeg 转码输出(stderr)解析时长(秒), 替代 ffprobe。失败返回 0。
    匹配形如: Duration: 00:03:21.45
    """
    try:
        match = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', ffmpegOutput)
        if match:
            hours, minutes, seconds = match.groups()
            duration = float(hours) * 3600 + float(minutes) * 60 + float(seconds)
            return duration if duration > 0 else 0
    except Exception:
        pass
    return 0


@bilimusic_bp.route('/bilimusic')
def biliMusicPage():
    return render_template('bilimusic.html')


@bilimusic_bp.route('/api/bilimusic/search', methods=['POST'])
def biliMusicSearch():
    keyword = request.json.get('keyword', '')
    useOldApi = request.json.get('useOldApi', False)

    if not keyword:
        return jsonify({'success': False, 'error': '关键词不能为空'})
    try:
        resultDict = bilimusic.bilibiliSearch(keyword, useOldApi)
        if isinstance(resultDict, tuple) and not resultDict[0]:
            return jsonify({'success': False, 'error': resultDict[1]})
        return jsonify({'success': True, 'data': resultDict})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@bilimusic_bp.route('/api/bilimusic/control', methods=['POST'])
def biliMusicControl():
    global currentBvid, isPlaying, isPaused, isStopped
    operation = request.json.get('operation', '')

    try:
        initMixer()

        if operation == 'play':
            mixer.music.stop()
            bvid = request.json.get('bvid', '')
            if not bvid:
                return jsonify({'success': False, 'error': '缺少bvid'})
            result = bilimusic.getFile(bvid)
            if not result[0]:
                return jsonify({'success': False, 'error': result[1]})
            fileObject = result[1]



            with open(m4aPath, 'wb') as f:
                f.write(fileObject)
            
            oldMp3Path = os.path.join(TEMP_DIR, MP3_FILE_NAME)
            try:
                os.remove(oldMp3Path)
            except Exception:
                pass

            mixer.music.unload()  # 解除文件占用

            convResult = m4aToMp3(m4aPath, mp3Path)
            if not convResult[0]:
                return jsonify({'success': False, 'error': 'ffmpeg转换失败: ' + convResult[1]})

            mixer.music.load(mp3Path)
            mixer.music.play()
            duration = convResult[2]
            currentBvid = bvid
            isPlaying = True
            isPaused = False
            isStopped = False
            return jsonify({'success': True, 'path': mp3Path, 'duration': duration})

        elif operation == 'stop':
            mixer.music.stop()
            isPlaying = False
            isPaused = False
            isStopped = True

        elif operation == 'pause':
            mixer.music.pause()
            isPaused = True
            isPlaying = False

        elif operation == 'resume':
            mixer.music.unpause()
            isPaused = False
            isPlaying = True

        elif operation == 'seek':
            seekSeconds = request.json.get('time', request.json.get('seekTime', 0))
            mixer.music.play(start=seekSeconds)

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@bilimusic_bp.route('/api/bilimusic/status')
def biliMusicStatus():
    global currentBvid, isPlaying, isPaused, isStopped
    try:
        if mixer.get_init():
            currentTime = mixer.music.get_pos() / 1000 if mixer.music.get_busy() else 0
            return jsonify({
                'success': True,
                'currentTime': currentTime,
                'isPlaying': isPlaying,
                'isPaused': isPaused,
                'isStopped': isStopped,
                'currentBvid': currentBvid
            })
        else:
            return jsonify({
                'success': True,
                'currentTime': 0,
                'isPlaying': False,
                'isPaused': False,
                'isStopped': True,
                'currentBvid': None
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})