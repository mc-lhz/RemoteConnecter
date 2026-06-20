# -*- coding: utf-8 -*-
"""屏幕模块 — 截图、MJPEG 推流、远程控制"""

import io
import time

from flask import Blueprint, Response, render_template, request
from PIL import ImageGrab
from pynput.keyboard import Controller as KeyboardController, Key
from pynput.mouse import Button
from pynput.mouse import Controller as MouseController

# 创建蓝图，挂载在 /screenshot
screen_bp = Blueprint('screen', __name__)

# ---- 控制器实例 ----
mouseController = MouseController()
keyboardController = KeyboardController()

SPECIAL_KEYS = {
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
MODIFIER_KEYS = {
    'ctrl': Key.ctrl,       'ctrl_l': Key.ctrl_l,     'ctrl_r': Key.ctrl_r,
    'alt': Key.alt,         'alt_l': Key.alt_l,       'alt_r': Key.alt_r,
    'shift': Key.shift,     'shift_l': Key.shift_l,   'shift_r': Key.shift_r,
    'cmd': Key.cmd,         'cmd_l': Key.cmd_l,       'cmd_r': Key.cmd_r,
}


@screen_bp.route('/screenshot')
def screenshot_page():
    """实时屏幕页面"""
    return render_template('screenshot.html')


@screen_bp.route('/screenshot/api/stream')
def screenshot_stream():
    """MJPEG 实时屏幕流 (约 10 FPS)"""
    def generate_frames():
        while True:
            screenshot = ImageGrab.grab()
            img_io = io.BytesIO()
            screenshot.save(img_io, 'JPEG', quality=80)
            frame_data = img_io.getvalue()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n'
                   b'Content-Length: %d\r\n\r\n' % len(frame_data))
            yield frame_data
            yield b'\r\n'

            time.sleep(0.05)

    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@screen_bp.route('/screenshot/api/control')
def screenshot_control():
    """远程控制 API — 鼠标点击 & 键盘输入（支持组合键如 ctrl+c）"""
    control_type = request.args.get('controlType', None)

    if control_type == 'mouse':
        # 鼠标点击：根据请求参数设置坐标和按钮
        x = request.args.get('x', None)
        y = request.args.get('y', None)
        button = Button.left if request.args.get('button', 'left') == 'left' else Button.right
        if x and y:
            mouseController.position = (int(x), int(y))
            mouseController.click(button, 1)
            return '鼠标点击成功'

    elif control_type == 'keyboard':
        keyStr = request.args.get('key', None)
        if keyStr:
            print(f'[键盘] 收到按键: {keyStr}')
            
            # 解析组合键：ctrl+c → ['ctrl','c']；shift+enter → ['shift','enter']
            keyList = keyStr.lower().split('+')
            modifiers = []   # 记录已按下的修饰键，最后逆序释放

            try:
                for key in keyList:
                    # 移除首尾空格
                    key = key.strip()  
                    if not key:
                        continue
                    if key in MODIFIER_KEYS:
                        # 修饰键：先按下
                        print(f'  按下修饰键: {key}')
                        keyboardController.press(MODIFIER_KEYS[key])
                        modifiers.append(MODIFIER_KEYS[key])
                    elif key in SPECIAL_KEYS:
                        # 特殊键：按下 + 释放
                        print(f'  按下特殊键: {key}')
                        keyboardController.press(SPECIAL_KEYS[key])
                        keyboardController.release(SPECIAL_KEYS[key])  
                    else:
                        # 普通字符
                        print(f'  按下普通键: {key}')
                        keyboardController.press(key)
                        keyboardController.release(key)

                # 释放所有修饰键（逆序）
                for modifier in reversed(modifiers):
                    print(f'  释放修饰键')
                    keyboardController.release(modifier)

                print('[键盘] 执行完成')
                return '键盘输入成功'
            except Exception as e:
                print(f'[键盘] 错误: {e}')
                return f'键盘输入失败: {str(e)}', 500

    return '无效操作', 400
