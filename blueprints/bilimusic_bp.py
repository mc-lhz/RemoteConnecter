from flask import Blueprint, request, jsonify, render_template
import os
import tempfile
import subprocess
import bilimusic
from pygame import mixer
from utils import resourcePath

bilimusic_bp = Blueprint('bilimusic', __name__)

TEMP_DIR = tempfile.gettempdir()
M4A_FILE_NAME = "RemoteConnecterBiliMusic.m4a"
WAV_FILE_NAME = "RemoteConnecterBiliMusic.wav"
m4aPath = os.path.join(TEMP_DIR, M4A_FILE_NAME)
wavPath = os.path.join(TEMP_DIR, WAV_FILE_NAME)
# 优先使用项目目录下的 ffmpeg.exe，找不到则使用系统 PATH 中的 ffmpeg
FFMPEG_PATH = resourcePath('ffmpeg.exe')
if not os.path.exists(FFMPEG_PATH):
    FFMPEG_PATH = 'ffmpeg'

# 根据 ffmpeg 路径推导同目录下的 ffprobe
if FFMPEG_PATH == 'ffmpeg':
    FFPROBE_PATH = 'ffprobe'
else:
    FFPROBE_PATH = os.path.join(os.path.dirname(FFMPEG_PATH), 'ffprobe.exe')
    if not os.path.exists(FFPROBE_PATH):
        FFPROBE_PATH = 'ffprobe'

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
    result = runFfmpeg(['-y', '-i', inputPath, '-vn', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2', outputPath])
    return result.returncode == 0, result.stderr.decode('utf-8', errors='ignore')


def getAudioDuration(path):
    """
    获取音频文件时长（秒），优先使用 ffprobe，失败返回 0
    """
    try:
        result = subprocess.run(
            [FFPROBE_PATH, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', path],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=10
        )
        if result.returncode == 0:
            duration = float(result.stdout.decode('utf-8', errors='ignore').strip())
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
    if not keyword:
        return jsonify({'success': False, 'error': '关键词不能为空'})
    try:
        resultDict = bilimusic.bilibiliSearch(keyword)
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
            duration = getAudioDuration(wavPath)
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