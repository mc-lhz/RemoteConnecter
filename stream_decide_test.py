# -*- coding: utf-8 -*-
"""自适应流测试：
① streamDecide 纯函数确定性单测
② 参数化帧大小对比（q80 全尺寸 vs scale=0.5 q40）
"""
import socket
import sys

sys.path.insert(0, r'D:\desktop\py\NewProject\RC-fork-auto')

import functions.screen.screen_bp as sb

# ---- ① 决策逻辑单测 ----
budget = 0.1  # 10fps

# a) 慢消费（lag 大）应逐帧升档到上限
level, streak = 0, 0
for _ in range(30):
    level, streak = sb.streamDecide(level, budget * 2.0, budget, streak)
assert level == len(sb.STREAM_LEVELS) - 1, f'慢消费应升到顶: {level}'
print('a) 慢消费升到顶档: PASS (level=%d)' % level)

# b) 畅通（lag 负）应慢升（60 帧一档）回 0
level, streak = len(sb.STREAM_LEVELS) - 1, 0
frames = 0
while level > 0 and frames < 10000:
    level, streak = sb.streamDecide(level, -budget * 0.5, budget, streak)
    frames += 1
assert level == 0 and frames >= sb.STREAM_RAISE_FRAMES * (len(sb.STREAM_LEVELS) - 1) - 5, \
    f'畅通应慢升回 0: level={level} frames={frames}'
print('b) 畅通慢升回 0: PASS (用了 %d 帧)' % frames)

# c) 迟滞防振荡（升档方向）：streak 未满 60 被拥塞帧打断即重置，
#    间歇性畅通永远不升档（拥塞帧 lag<50% 预算不降档、只清 streak）
level, streak = 2, 0
for _ in range(50):
    for _ in range(59):
        level, streak = sb.streamDecide(level, -budget * 0.5, budget, streak)
    level, streak = sb.streamDecide(level, budget * 0.3, budget, streak)  # 打断
assert level == 2 and streak == 0, f'间歇畅通不应升档: {level},{streak}'
print('c) 升档迟滞（streak 打断重置）: PASS')

# d) 中间 lag（0 < lag < 50% 预算）保持档位不累积 streak
level, streak = 2, 0
for _ in range(200):
    level, streak = sb.streamDecide(level, budget * 0.2, budget, streak)
assert level == 2 and streak == 0, f'中等 lag 应保持: {level},{streak}'
print('d) 中等 lag 保持档位: PASS')

# ---- ② 参数化帧大小对比（解析 MJPEG 前几帧的 Content-Length）----
import urllib.request

def firstFrameSizes(url, count=3, timeout=8):
    """读流前 N 帧头，返回 Content-Length 列表"""
    sizes = []
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        buf = b''
        while len(sizes) < count:
            chunk = resp.read(4096)
            if not chunk:
                break
            buf += chunk
            while True:
                marker = buf.find(b'Content-Length: ')
                if marker < 0:
                    break
                end = buf.find(b'\r\n', marker)
                if end < 0:
                    buf = buf[marker:]
                    break
                sizes.append(int(buf[marker + 16:end]))
                buf = buf[end + 2:]
                if len(sizes) >= count:
                    break
            if len(sizes) >= count:
                break
    return sizes

try:
    full = firstFrameSizes('http://127.0.0.1:8772/screenshot/api/stream?auto=0&fps=5', 2)
    small = firstFrameSizes('http://127.0.0.1:8772/screenshot/api/stream?auto=0&scale=0.5&quality=40&fps=5', 2)
    print('全尺寸 q80 帧字节:', full)
    print('scale0.5 q40 帧字节:', small)
    ratio = sum(small) / max(1, sum(full))
    print('带宽比: %.1f%%（节省 %.0f%%）' % (ratio * 100, (1 - ratio) * 100))
    ok_size = ratio < 0.5
    print('参数化帧大小对比:', 'PASS' if ok_size else 'FAIL')
except Exception as e:
    print('帧大小对比异常:', e)
    ok_size = False

ok = ok_size
print('总体:', 'PASS' if ok else 'FAIL')
raise SystemExit(0 if ok else 1)
