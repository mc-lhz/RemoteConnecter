# -*- coding: utf-8 -*-
"""屏幕模块 — 截图、MJPEG 推流、远程控制"""

import io
import time

from flask import Blueprint, Response, jsonify, render_template, request
from PIL import ImageChops, ImageGrab
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


@screen_bp.route('/screenshot/api/size')
def screenshotSize():
    """真实屏幕分辨率 (点击映射使用; 流可能按 scale 缩放, naturalWidth 不可靠)"""
    shot = ImageGrab.grab()
    return jsonify({'width': shot.width, 'height': shot.height})


def _streamParam(name, default, low, high, cast=float):
    try:
        value = cast(request.args.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


@screen_bp.route('/screenshot/api/stream')
def screenshotStream():
    """MJPEG 实时屏幕流。

    参数: fps(1-20, 默认10) / quality(30-95, 默认80) / scale(0.25-1, 默认1)。
    静止帧跳过: 画面无变化时不编码不发送 (最长 2s 补发一帧保连接), 大幅省带宽与 CPU。
    """
    fps = _streamParam('fps', 10, 1, 20)
    quality = _streamParam('quality', 80, 30, 95, int)
    scale = _streamParam('scale', 1.0, 0.25, 1.0)
    interval = 1.0 / fps
    keepAliveSeconds = 2.0

    def generateFrames():
        prevThumb = None
        lastSent = 0.0
        while True:
            started = time.time()
            screenshot = ImageGrab.grab()
            if scale < 1.0:
                screenshot = screenshot.resize(
                    (max(1, int(screenshot.width * scale)), max(1, int(screenshot.height * scale))))
            thumb = screenshot.convert('L').resize((160, 90))
            changed = prevThumb is None or ImageChops.difference(prevThumb, thumb).getbbox() is not None
            now = time.time()
            if changed or (now - lastSent) > keepAliveSeconds:
                imgIo = io.BytesIO()
                screenshot.save(imgIo, 'JPEG', quality=quality)
                frameData = imgIo.getvalue()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: %d\r\n\r\n' % len(frameData))
                yield frameData
                yield b'\r\n'
                prevThumb = thumb
                lastSent = now
            elapsed = time.time() - started
            if elapsed < interval:
                time.sleep(interval - elapsed)

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