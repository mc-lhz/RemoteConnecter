# -*- coding: utf-8 -*-
"""更新功能测试：compareVersion 单测 + check API 实测"""
import json
import sys
import urllib.request

sys.path.insert(0, r'D:\desktop\py\NewProject\RC-fork-auto')

from functions.update import repoUpdate

# ---- ① compareVersion 单测 ----
cases = [
    ('v1.8.0', 'v1.7.1', 1),
    ('v1.7.1', 'v1.7.1', 0),
    ('v1.7.0', 'v1.7.1', -1),
    ('v2.0.0', 'v1.9.9', 1),
    ('v1.8.0-beta.1', 'v1.8.0', -1),      # 预发布 < 正式
    ('v1.8.0', 'v1.8.0-beta.1', 1),
    ('v1.8.0-beta.2', 'v1.8.0-beta.1', 0),  # 预发布号不比较（简化语义）
    ('1.8.0', '1.7.1', 1),                # 无 v 前缀
    ('v1.10.0', 'v1.9.0', 1),             # 数字段非字符串比较
    ('v1.7', 'v1.7.0', 0),                # 缺段补 0
    ('', 'v1.7.1', -1),                   # 空串按 0.0.0
    ('v1.7.1', '', 1),
]
fails = []
for a, b, expect in cases:
    got = repoUpdate.compareVersion(a, b)
    if got != expect:
        fails.append((a, b, expect, got))
print('compareVersion 用例 %d 项，失败 %d 项' % (len(cases), len(fails)))
for f in fails:
    print('  FAIL:', f)
ok_unit = not fails

# ---- ② /update/api/check 实测（8771 fork 宿主）----
try:
    with urllib.request.urlopen('http://127.0.0.1:8771/update/api/check', timeout=30) as r:
        data = json.loads(r.read().decode('utf-8'))
    print('check API 响应:', json.dumps(data, ensure_ascii=False))
    ok_api = (data.get('current') == 'v1.7.1' and data.get('latest')
              and isinstance(data.get('updateAvailable'), bool)
              and 'RemoteConnecter/releases' in data.get('assetUrl', ''))
except Exception as e:
    print('check API 异常:', e)
    ok_api = False

print('总体:', 'PASS' if (ok_unit and ok_api) else 'FAIL')
raise SystemExit(0 if (ok_unit and ok_api) else 1)