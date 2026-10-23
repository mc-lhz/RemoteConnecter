# -*- coding: utf-8 -*-
"""proxy 插件 — 本地反向代理 (移植 GithubMirror 三层改写思路)

请求链路:
    浏览器 -> /proxy/direct/<完整上游URL> -> requests 转发 -> 上游
    上游 HTML 响应经 bs4 改写: 绝对 URL 全部改写为 /proxy/direct/... ,
    并注入 head 内联脚本 (patch fetch/XHR), 使页面所有资源都走本地代理,
    绕开本地 hosts 指向 127.0.0.1 触发的 Chrome Private Network Access 拦截。
"""
import json
import os
import re

import requests
from bs4 import BeautifulSoup
from flask import Blueprint, request, jsonify, Response

# 获取插件id (以 __file__ 锚定, 不依赖运行时 CWD)
pluginDir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(pluginDir, 'plugin.json'), encoding='utf-8-sig') as f:
    pluginID = json.load(f)['id']

proxy_bp = Blueprint(f'{pluginID}_bp', __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path=f'/{pluginID}/static')

# 上游请求超时(秒), 防止目标站无响应导致 worker 线程挂死
REQUEST_TIMEOUT = 20
# 代理路径前缀 (浏览器侧相对路径, 浏览器拼 origin 后即为 /proxy/direct/<上游URL>)
PROXY_PREFIX = f'/{pluginID}/direct/'

# 逐跳头(hop-by-hop): 请求转发与响应回传都不透传, 由 requests/Flask 按各自目标重新生成
HOP_BY_HOP_HEADERS = {
    'host', 'connection', 'keep-alive', 'proxy-authenticate',
    'proxy-authorization', 'te', 'trailer', 'transfer-encoding',
    'upgrade', 'content-length', 'content-encoding',
}
# 上游安全头: 删除 CSP 避免源站策略误杀注入脚本/代理子资源
STRIP_RESPONSE_HEADERS = {
    'content-security-policy', 'content-security-policy-report-only',
}

# HTML 属性改写清单: [(标签, 属性), ...] (对齐 GithubMirror 显式选择器清单)
URL_ATTR_MAP = [
    ('a', 'href'), ('area', 'href'), ('link', 'href'),
    ('script', 'src'), ('img', 'src'), ('iframe', 'src'), ('embed', 'src'),
    ('source', 'src'), ('video', 'src'), ('audio', 'src'),
    ('form', 'action'),
    ('link', 'data-href'), ('link', 'data-base-href'),
    ('img', 'data-src'),
    ('meta', 'content'),
]
# srcset 单独处理 (bs4 将其解析为 (url, 描述符) 元组列表)
SRCSET_TAGS = ('img', 'source')

ABS_URL_RE = re.compile(r'^https?://', re.I)

# 首屏注入脚本: patch window.fetch(含 Request 对象) 与 XHR.open,
# 把页面 JS 运行时发起的绝对 URL 请求改写为经 /proxy/direct/ 走本地代理
INJECT_SCRIPT = """
(function(){
  var PREFIX = '__PREFIX__';
  function rewrite(url){
    if (typeof url !== 'string') return url;
    if (url.indexOf(PREFIX) === 0) return url;
    if (!/^https?:\\/\\//i.test(url)) return url;
    return location.origin + PREFIX + url;
  }
  var nativeFetch = window.fetch;
  if (nativeFetch) {
    window.fetch = function(input, init){
      if (input instanceof Request) {
        var newUrl = rewrite(input.url);
        if (newUrl !== input.url) input = new Request(newUrl, input);
      } else {
        input = rewrite(input);
      }
      return nativeFetch.call(this, input, init);
    };
  }
  var nativeOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url, asyncFlag, user, password){
    return nativeOpen.call(this, method, rewrite(url), asyncFlag, user, password);
  };
})();
""".replace('__PREFIX__', PROXY_PREFIX)


def rewriteOneUrl(urlString):
    """绝对 http(s) URL -> /proxy/direct/<原URL>; 相对/非 http(s)/已是代理前缀的原样返回"""
    if not isinstance(urlString, str) or not ABS_URL_RE.match(urlString):
        return urlString
    if urlString.startswith(PROXY_PREFIX):
        return urlString
    return PROXY_PREFIX + urlString


def rewriteSrcset(value):
    """srcset: 逗号分隔的「URL + 描述符」串, 逐段改写首段 URL 后还原 (bs4 html.parser 下为字符串)"""
    if not isinstance(value, str) or not value:
        return value
    parts = []
    for segment in value.split(','):
        tokens = segment.strip().split(None, 1)
        if not tokens:
            continue
        parts.append(' '.join(t for t in (rewriteOneUrl(tokens[0]), tokens[1] if len(tokens) > 1 else '') if t))
    return ', '.join(parts)


def rewriteHtml(htmlText):
    """bs4 解析 HTML: 改写全部绝对 URL + 注入 head 首屏脚本, 返回序列化字符串"""
    soup = BeautifulSoup(htmlText, 'html.parser')
    for tag, attrName in URL_ATTR_MAP:
        for element in soup.find_all(tag):
            oldValue = element.get(attrName)
            if oldValue is None:
                continue
            newValue = rewriteOneUrl(oldValue)
            if newValue != oldValue:
                element[attrName] = newValue
    for tag in SRCSET_TAGS:
        for element in soup.find_all(tag):
            oldValue = element.get('srcset')
            if oldValue is None:
                continue
            newValue = rewriteSrcset(oldValue)
            if newValue != oldValue:
                element['srcset'] = newValue
    # 注入首屏脚本到 head (无 head 则创建)
    headTag = soup.head
    if headTag is None:
        headTag = soup.new_tag('head')
        if soup.html:
            soup.html.insert(0, headTag)
        else:
            soup.insert(0, headTag)
    scriptTag = headTag.new_tag('script')
    scriptTag.string = INJECT_SCRIPT
    headTag.append(scriptTag)
    return str(soup)


@proxy_bp.route(f'/{pluginID}')
def proxyHome():
    return f'''<h3>{pluginID}</h3>
    <a href='{PROXY_PREFIX}https://github.com'>github (经代理)</a><br>
    <a href='{PROXY_PREFIX}https://cn.bing.com'>cn.bing (经代理)</a><br>
    <p>用法: 浏览器地址栏访问 {PROXY_PREFIX}&lt;完整上游URL&gt;</p>
    '''


@proxy_bp.route(f'{PROXY_PREFIX}<path:url>')
def direct(url):
    # 仅放行 http(s) 目标, 其余 scheme (file:// 等) 拒绝
    if not ABS_URL_RE.match(url):
        return jsonify({'error': 'only http(s) url allowed'}), 400
    # 过滤逐跳头, 避免把本地 Host/Content-Length 等透传给目标站
    forwardedHeaders = {
        key: value for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }
    body = request.get_data() if request.method not in ('GET', 'HEAD') else None
    try:
        # allow_redirects=False: 3xx 交回浏览器, 并把 Location 改写走代理, 避免直连 loopback
        upstreamResponse = requests.request(
            method=request.method,
            url=url,
            headers=forwardedHeaders,
            data=body,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
            verify=False,
        )
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'upstream request failed: {e}'}), 502

    outHeaders = {
        key: value for key, value in upstreamResponse.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
        and key.lower() not in STRIP_RESPONSE_HEADERS
    }
    # 3xx: Location 若为绝对 http(s) URL, 改写为走代理
    if 300 <= upstreamResponse.status_code < 400:
        location = outHeaders.get('Location') or outHeaders.get('location')
        if location:
            newLocation = rewriteOneUrl(location.strip())
            if newLocation != location.strip():
                outHeaders['Location'] = newLocation

    # 2xx/3xx 的 text/html: bs4 改写绝对 URL + 注入首屏脚本
    contentType = (upstreamResponse.headers.get('Content-Type') or '').lower()
    if 200 <= upstreamResponse.status_code < 400 and 'text/html' in contentType:
        # 从 Content-Type 解析 charset, 无则 utf-8 (避免 apparent_encoding 全量扫描的开销)
        charset = 'utf-8'
        for part in contentType.split(';'):
            part = part.strip().lower()
            if part.startswith('charset='):
                charset = part.split('=', 1)[1].strip()
                break
        try:
            htmlText = upstreamResponse.content.decode(charset, errors='replace')
            htmlText = rewriteHtml(htmlText)
            return Response(htmlText, status=upstreamResponse.status_code, headers=outHeaders)
        except Exception as e:
            # 改写失败不阻断, 原样透传
            print(f'[{pluginID}] html rewrite failed: {e}')

    return Response(
        upstreamResponse.content,
        status=upstreamResponse.status_code,
        headers=outHeaders,
    )
