import requests
from flask import Blueprint, request, jsonify, redirect

proxy_bp = Blueprint('proxy_bp', __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/proxy/static')

# 逐跳头（hop-by-hop）：代理转发时不应透传，交由 requests 按目标 URL 重新生成
HOP_BY_HOP_HEADERS = {
    'host', 'connection', 'keep-alive', 'proxy-authenticate',
    'proxy-authorization', 'te', 'trailer', 'transfer-encoding',
    'upgrade', 'content-length', 'content-encoding',
}

@proxy_bp.route('/proxy')
def proxy():
    return '''<a href='/proxy/direct'>Direct</a>
    <br>
    <a href='/proxy/cf'>cf</a>
    '''
@proxy_bp.route('/proxy/direct/<path:url>')
def direct(url):
    print(url)
    # 请求反向代理：浏览器请求/proxy/direct/https://example.com，服务端转发
    method = request.method
    # 过滤逐跳头，避免把本地 Host/Origin 等透传给目标站触发风控
    forwardedHeaders = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }
    print(forwardedHeaders)

    if method == 'GET':
        response = requests.get(url, headers=forwardedHeaders, verify=False)
    elif method == 'POST':
        response = requests.post(url, headers=forwardedHeaders, data=request.data, verify=False)
    return response.text
@proxy_bp.route('/proxy/proxy/cf')
def cf():
    return jsonify({'message': 'Hello, World!'})

