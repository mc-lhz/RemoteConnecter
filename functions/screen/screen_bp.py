# -*- coding: utf-8 -*-
"""屏幕模块 — 截图、MJPEG 推流、远程控制"""

import io
import time

from flask import Blueprint, Response, render_template, request
from PIL import Image, ImageGrab
from pynput.keyboard import Controller as KeyboardController, Key
from pynput.mouse import Button
from pynput.mouse import Controller as MouseController

import Logcat

Log = Logcat.Logcat()

# 创建蓝图，页面路由为 /screenshot
screen_bp = Blueprint('screen', __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/screen/static')

# ---- 控制器实例 ----
mouseController = MouseController()
keyboardController = KeyboardController()

specialKeys = {
    # ---- 导航键 ----
    'enter': Key.enter,       'space': Key.space,       'tab': Key.tab,
    'backspace': Key.backspace, 'delete': Key.delete,   'esc': Key.esc,
    'up': Key.up,             'down': Key.down,         'left': Key.left,
    'right': Key.right,       'home': Key.home,         'end': Key.end,
    'page_up': Key.page_up,   'page_down': Key.page_down,
    'insert': Key.insert,     'menu': Key.menu,         'pause': Key.pause,
    'print_screen': Key.print_screen,
    # ---- 修饰键 ----
    'ctrl': Key.ctrl,         'ctrl_l': Key.ctrl_l,    'ctrl_r': Key.ctrl_r,
    'alt': Key.alt,           'alt_l': Key.alt_l,       'alt_r': Key.alt_r,
    'shift': Key.shift,       'shift_l': Key.shift_l,   'shift_r': Key.shift_r,
    'cmd': Key.cmd,           'cmd_l': Key.cmd_l,       'cmd_r': Key.cmd_r,
    'alt_gr': getattr(Key, 'alt_gr', Key.alt),
    # ---- 锁定键 ----
    'caps_lock': Key.caps_lock,
    'num_lock': Key.num_lock,
    'scroll_lock': Key.scroll_lock,
    # ---- F1-F24 ----
    'f1': Key.f1,   'f2': Key.f2,   'f3': Key.f3,   'f4': Key.f4,
    'f5': Key.f5,   'f6': Key.f6,   'f7': Key.f7,   'f8': Key.f8,
    'f9': Key.f9,   'f10': Key.f10, 'f11': Key.f11, 'f12': Key.f12,
    'f13': Key.f13, 'f14': Key.f14, 'f15': Key.f15, 'f16': Key.f16,
    'f17': Key.f17, 'f18': Key.f18, 'f19': Key.f19, 'f20': Key.f20,
    # ---- 媒体键 ----
    'media_volume_up': Key.media_volume_up,
    'media_volume_down': Key.media_volume_down,
    'media_volume_mute': Key.media_volume_mute,
    'media_play_pause': Key.media_play_pause,
    'media_next': Key.media_next,
    'media_previous': Key.media_previous,
}

# 修饰键映射（用于组合键解析，如 ctrl+c）
modifierKeys = {
    'ctrl': Key.ctrl,       'ctrl_l': Key.ctrl_l,     'ctrl_r': Key.ctrl_r,
    'alt': Key.alt,         'alt_l': Key.alt_l,       'alt_r': Key.alt_r,
    'shift': Key.shift,     'shift_l': Key.shift_l,   'shift_r': Key.shift_r,
    'cmd': Key.cmd,         'cmd_l': Key.cmd_l,       'cmd_r': Key.cmd_r,
    'alt_gr': getattr(Key, 'alt_gr', Key.alt),
}


@screen_bp.route('/screenshot')
def screenshotPage():
    """实时屏幕页面"""
    return render_template('screenshot.html')


# ---- 自适应流：档位表与决策（纯函数，便于确定性测试）----
# 公网瓶颈在客户端下行/服务端上行：客户端消费不动时 socket 缓冲填满，
# 生成器的下一帧 yield 会被 werkzeug 写阻塞——帧起点间隔因此拉长。
# 用帧间隔的 EMA 超出预算的部分（lag）判断拥塞：慢则快降档（画质/
# 缩小分辨率），持续畅通则慢升档。迟滞防振荡：降档阈值低、升档阈值高。
STREAM_LEVELS = [
    # (quality, scale)  level 0 = 全速原画质
    (80, 1.00),
    (65, 0.85),
    (55, 0.70),
    (45, 0.55),
    (35, 0.45),
    (30, 0.35),
]
STREAM_RAISE_FRAMES = 60      # 连续畅通 60 帧（约 6s@10fps）才升一档
STREAM_DROP_LAG_RATIO = 0.5   # EMA lag 超过预算 50% 即降档
STREAM_RAISE_LAG = 0.0        # EMA lag ≤ 0 视为畅通
STREAM_EMA_ALPHA = 0.1


def streamDecide(level, emaLag, budget, fastStreak):
    """根据平滑滞后调整档位。返回 (newLevel, newFastStreak)。"""
    if emaLag > budget * STREAM_DROP_LAG_RATIO and level < len(STREAM_LEVELS) - 1:
        return level + 1, 0
    if emaLag <= STREAM_RAISE_LAG and level > 0:
        fastStreak += 1
        if fastStreak >= STREAM_RAISE_FRAMES:
            return level - 1, 0
        return level, fastStreak
    return level, 0 if emaLag > STREAM_RAISE_LAG else fastStreak


def _floatArg(name, default, low, high):
    try:
        value = float(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


@screen_bp.route('/screenshot/api/stream')
def screenshotStream():
    """MJPEG 实时屏幕流。

    参数: scale(0.1~1 缩放) quality(10~95) fps(1~30 上限) auto(0/1 自适应, 默认开)
    自适应依据客户端消费速度自动降/升画质档，公网慢链路自动让出带宽。
    """
    scale = _floatArg('scale', 1.0, 0.1, 1.0)
    quality = int(_floatArg('quality', 80, 10, 95))
    fps = _floatArg('fps', 10, 1, 30)
    auto = request.args.get('auto', '1') != '0'
    budget = 1.0 / fps

    def generateFrames():
        level = 0
        emaLag = 0.0
        fastStreak = 0
        lastFrameStart = time.time()
        while True:
            frameStart = time.time()
            interval = frameStart - lastFrameStart
            lastFrameStart = frameStart
            emaLag = (1 - STREAM_EMA_ALPHA) * emaLag + STREAM_EMA_ALPHA * (interval - budget)
            if auto:
                level, fastStreak = streamDecide(level, emaLag, budget, fastStreak)
                frameQuality, frameScale = STREAM_LEVELS[level]
                frameQuality = min(quality, frameQuality)
                frameScale = min(scale, frameScale)
            else:
                frameQuality, frameScale = quality, scale

            screenshot = ImageGrab.grab()
            if frameScale < 0.999:
                screenshot = screenshot.resize(
                    (max(1, int(screenshot.width * frameScale)),
                     max(1, int(screenshot.height * frameScale))),
                    Image.BILINEAR)
            imgIo = io.BytesIO()
            screenshot.save(imgIo, 'JPEG', quality=frameQuality)
            frameData = imgIo.getvalue()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n'
                   b'Content-Length: %d\r\n\r\n' % len(frameData))
            yield frameData
            yield b'\r\n'

            elapsed = time.time() - frameStart
            if elapsed < budget:
                time.sleep(budget - elapsed)
            # 编码超预算时不 sleep，直接赶下一帧（lag 信号会让自适应降档）

    return Response(generateFrames(), mimetype='multipart/x-mixed-replace; boundary=frame')


def _buttonOf(name):
    return Button.right if name == 'right' else Button.left


def _intArg(name, default=0):
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


@screen_bp.route('/screenshot/api/control')
def screenshotControl():
    """远程控制 API — 鼠标点击/移动/滚轮/拖拽 & 键盘输入（支持组合键如 ctrl+c）"""
    controlType = request.args.get('controlType', None)

    if controlType == 'mouse':
        # 鼠标点击：坐标 + 按钮 + 次数（2=双击）
        x = request.args.get('x', None)
        y = request.args.get('y', None)
        button = _buttonOf(request.args.get('button', 'left'))
        count = max(1, min(_intArg('count', 1), 3))
        if x is not None and y is not None:
            mouseController.position = (_intArg('x'), _intArg('y'))
            mouseController.click(button, count)
            return '鼠标点击成功'

    elif controlType == 'move':
        # 仅移动（拖拽过程中的位置更新）
        if request.args.get('x') is not None and request.args.get('y') is not None:
            mouseController.position = (_intArg('x'), _intArg('y'))
            return '鼠标移动成功'

    elif controlType == 'wheel':
        # 滚轮：dx 水平 dy 垂直（正值为向上/右）
        dx = max(-10, min(_intArg('dx'), 10))
        dy = max(-10, min(_intArg('dy'), 10))
        if dx or dy:
            mouseController.scroll(dx, dy)
        return '滚轮成功'

    elif controlType == 'press':
        # 按下鼠标（配合 move + release 实现拖拽）
        mouseController.press(_buttonOf(request.args.get('button', 'left')))
        return '鼠标按下成功'

    elif controlType == 'release':
        # 释放鼠标
        mouseController.release(_buttonOf(request.args.get('button', 'left')))
        return '鼠标释放成功'

    elif controlType == 'keyboard':
        # 支持两种传参：keys 多参数逐键传输（keys=shift&keys=%2B，可表达
        # 任意字符包括 '+'）；旧版单 key 参数按 '+' 分隔组合键字符串
        keyList = [k.lower() for k in request.args.getlist('keys') if k]
        if not keyList:
            keyString = request.args.get('key', None)
            if keyString:
                Log.i('Keyboard', f'收到按键: {keyString}')
                # 解析组合键：ctrl+c → ['ctrl','c']；shift+enter → ['shift','enter']
                keyList = keyString.lower().split('+')
        if keyList:
            modifiers = []   # 记录已按下的修饰键，最后逆序释放

            try:
                for key in keyList:
                    # 移除首尾空格
                    key = key.strip()
                    if not key:
                        continue
                    if key in modifierKeys:
                        # 修饰键：先按下
                        Log.d('Keyboard', f'按下修饰键: {key}')
                        keyboardController.press(modifierKeys[key])
                        modifiers.append(modifierKeys[key])
                    elif key in specialKeys:
                        # 特殊键：按下 + 释放
                        Log.d('Keyboard', f'按下特殊键: {key}')
                        keyboardController.press(specialKeys[key])
                        keyboardController.release(specialKeys[key])
                    else:
                        # 普通字符
                        Log.d('Keyboard', f'按下普通键: {key}')
                        keyboardController.press(key)
                        keyboardController.release(key)

                # 释放所有修饰键（逆序）
                for modifier in reversed(modifiers):
                    Log.d('Keyboard', '释放修饰键')
                    keyboardController.release(modifier)

                Log.i('Keyboard', '执行完成')
                return '键盘输入成功'
            except Exception as e:
                Log.e('Keyboard', f'错误: {e}')
                return f'键盘输入失败: {str(e)}', 500

    return '无效操作', 400