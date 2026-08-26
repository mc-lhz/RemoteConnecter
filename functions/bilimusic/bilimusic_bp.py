from flask import Blueprint, request, jsonify, render_template
import os
import re
import tempfile
import subprocess
from . import bilimusic
from pygame import mixer
from utils import resourcePath

bilimusic_bp = Blueprint('bilimusic', __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/bilimusic/static')

TEMP_DIR = tempfile.gettempdir()
# 临时文件名
M4A_FILE_NAME = "RemoteConnecterBiliMusic.m4a"
WAV_FILE_NAME = "RemoteConnecterBiliMusic.wav"
m4aPath = os.path.join(TEMP_DIR, M4A_FILE_NAME)
wavPath = os.path.join(TEMP_DIR, WAV_FILE_NAME)
# 优先使用项目目录下的 ffmpeg.exe，找不到则使用系统 PATH 中的 ffmpeg
# 注: 使用完整版 ffmpeg (含 wav muxer + pcm_s16le), 输出 wav 无重编码, 极快且无损;
#     时长改由 ffmpeg 转码输出解析, 见 parseDuration()。
FFMPEG_PATH = resourcePath('bin/ffmpeg.exe')
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


def m4aToWav(inputPath, outputPath):
    # 完整版 ffmpeg (含 wav muxer + pcm_s16le): m4a -> wav。
    # 仅解码写 PCM, 无重编码, 极快且无损; 时长由 ffmpeg 输出解析 (parseDuration)。
    # 使用此函数时, 请将 FFMPEG_PATH 指向含 wav 输出的完整版 ffmpeg.exe。
    result = runFfmpeg(['-y', '-i', inputPath, '-vn', '-acodec', 'pcm_s16le', outputPath])
    success = result.returncode == 0
    errMsg = result.stderr.decode('utf-8', errors='ignore')
    duration = parseDuration(errMsg)
    return success, errMsg, duration


def m4aToMp3(inputPath, outputPath):
    # 精简版 ffmpeg-mini (仅 mp3 muxer + libmp3lame): m4a -> mp3。
    # 用 -b:a 320k 固定高码率, 减轻 AAC->MP3 二次有损转码的音质损失
    # (mini 构建未指定 -b:a 时 LAME 默认 128k, 对高码率原档损失明显)。
    # 使用此函数时, 请将 FFMPEG_PATH 指向 mp3-only 的 ffmpeg-mini.exe。
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


# strict_slashes=False: 容忍 /bilimusic 与 /bilimusic/ 两种写法,
# 避免首页 iframe 访问 /bilimusic 时被 Flask 308 重定向导致加载失败
@bilimusic_bp.route('/bilimusic', strict_slashes=False)
def biliMusicPage():
    return render_template('bilimusic.html')


@bilimusic_bp.route('/bilimusic/api/search', methods=['POST'])
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


@bilimusic_bp.route('/bilimusic/api/control', methods=['POST'])
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
            
            oldWavPath = os.path.join(TEMP_DIR, WAV_FILE_NAME)
            try:
                os.remove(oldWavPath)
            except Exception:
                pass

            mixer.music.unload()  # 解除文件占用
            convResult = m4aToWav(m4aPath, wavPath)
            
            if not convResult[0]:
                return jsonify({'success': False, 'error': 'ffmpeg转换失败: ' + convResult[1]})

            mixer.music.load(wavPath)
            mixer.music.play()
            duration = convResult[2]
            currentBvid = bvid
            isPlaying = True
            isPaused = False
            isStopped = False
            return jsonify({'success': True, 'path': wavPath, 'duration': duration})

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


@bilimusic_bp.route('/bilimusic/api/status')
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