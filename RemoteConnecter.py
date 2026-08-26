# -*- coding: utf-8 -*-
"""RemoteConnecter — 学校电脑管理系统 (Flask 多模块版)"""

'''
传统提问模型
你提问 -》他回答

智能体Agent
你给目标 -》 它自主完成
可调用工具、读写文件、执行代码

1.辅助编程
自然语言描述需求
验证特征或者模型的想法

2.自主研究
选定方向 -》 ...

了解、学习和使用AI
掌握扎实的专业基础
培养提问题的能力

推荐系统
1.协同过滤
找相似用户

矩阵分解：拆解用户和商品 计算用户-商品的相似度

2.嵌入向量空间
将内容变为向量

真实世界：
三级漏斗：
1.召回阶段：1000个候选
2.精排：计算概率
3.多样性

双塔
用户塔、视频塔
生成向量
计算内积
获得前1000物品

精排
早期：点击率 -> 标题党
现在：多目标学习：同时预测多个目标（点、完播、一键三连）

Multi-Goal AI
不同预测目标

问题：黑盒打分器

LLM：
1.零样本理解
2.自然语言
3.可解释性

1.构建提示词（兴趣、清单）
2.输入大模型

与算法对话、调整

注意力头：大模型放入模型，多元能力

需要用户 需要待推荐物品

LLM终极形态：重新定义语言
针对兴趣推荐模型
直接根据偏好、浏览历史生成推荐列表‘
不需要召回、重排

AI时代的底层能力
1.底层能力
核心：条件概率
了解核心与原理比使用更重要

AI替代大部分重复性的编码，但不能完全替代人类的判断和理解

2.审美
什么样的AI项目眼前一亮，什么坑容易踩
是创造，不是模仿
做好好事情

3.评审项目时
科创在于创新，问题存在没被解决
用技术解决掉
问题-匹配的技术
更看见发现-解决问题

4.资源、技术有限怎么办
用大模型筛选、预处理
做可行性分析
技术选取偏好
机器的使用工具
可以用大模型，也可用小模型

5.界限
“技术酷就行”  保持技术温度
技术来自多样性
初心：提高效率，不是做恶的事情

6.行动：寄语
保持初心，激发兴趣活力

'''

import sys
import os
import ctypes
from flask import Flask
import Logcat
from utils import *
from functions.main.main_bp import main_bp
from functions.main.file_bp import file_bp
from functions.screen.screen_bp import screen_bp
from functions.update.update_bp import update_bp
from functions.bilimusic.bilimusic_bp import bilimusic_bp
from functions.term.term_bp import term_bp, sock  # 终端 (WS / ConPTY)
# ---- Windows DPI 感知设置 (必须在最开始设置) ----
if sys.platform == 'win32':
    try:
        # 设置 DPI 感知级别为 Per Monitor DPI Aware V2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            # 回退到系统级 DPI 感知
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# ---- 创建应用 ----
# 各蓝图自带 template_folder/static_folder，主应用无需全局指定
app = Flask(__name__)
app.template_folder = None
app.static_folder = None

# ---- 根路径首页 (重定向到 main 蓝图) ----
@app.route('/')
def root():
    from flask import redirect
    return redirect('/main/')


# ---- 公共静态资源 (shared/static, 多个蓝图共享) ----
@app.route('/shared/static/<path:filename>')
def sharedStatic(filename):
    from flask import send_from_directory
    return send_from_directory(resourcePath('functions/shared/static'), filename)


# ---- 注册蓝图 ----
app.register_blueprint(main_bp)       # 主页 & 终端 (/main)
app.register_blueprint(file_bp)       # 文件浏览 / 下载 / 上传
app.register_blueprint(screen_bp)     # 屏幕截图 / 推流 / 远程控制 (/screen)
app.register_blueprint(update_bp)     # 更新管理 (/update)
app.register_blueprint(bilimusic_bp)  # B 站视频搜索 / 下载音频 (/bilimusic)
app.register_blueprint(term_bp)       # 终端 (term) — 页面 /term/terminal + API /terminal/api/ws
sock.init_app(app)                    # 终端 WebSocket
# ---- 启动 ----
if __name__ == '__main__':
    Logcat.Logcat().i('Main', getPythonVersion())
    app.run(host='0.0.0.0', port=80, debug=True, use_reloader=True)
