import requests


# 旧版接口请求头
searchHeaders = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "cache-control": "max-age=0",
    "priority": "u=0, i",
    "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Microsoft Edge\";v=\"133\", \"Chromium\";v=\"133\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
}

getFileHeaders = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "cache-control": "max-age=0",
        "priority": "u=0, i",
        "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Microsoft Edge\";v=\"133\", \"Chromium\";v=\"133\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
    }

# 新版接口请求头
newSearchHeaders = {
    "authority": "api.bilibili.com",
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9",
    "origin": "https://search.bilibili.com",
    "referer": "https://search.bilibili.com/all?keyword=1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0",
    "sec-ch-ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


def bilibiliSearchOld(keyword: str):
    """
    旧版搜索接口
    """
    searchUrl = f"https://api.bilibili.com/x/web-interface/search/type?&keyword={keyword}&search_type=video"
    retryCount = 1
    maxRetries = 20

    while retryCount <= maxRetries:
        response = requests.get(searchUrl, headers=searchHeaders)
        if response.status_code == 200:
            break
        elif response.status_code == 412:
            print(f"请求被拒绝，正在重试 {response.text} 次数：{retryCount}")
            retryCount += 1
            continue
        else:
            return False, f"请求失败，状态码：{response.status_code}"

    data = response.json()
    searchList = data['data']['result']
    for item in searchList:
        item['title'] = item.get('title', '').replace('<em class="keyword">', '').replace('</em>', '')
    return searchList


def bilibiliSearchNew(keyword: str):
    """
    新版搜索接口（wbi/search/all/v2）
    返回统一格式：{bvid, title, author}
    """
    searchUrl = f"https://api.bilibili.com/x/web-interface/wbi/search/all/v2?page=1&keyword={keyword}"
    try:
        response = requests.get(searchUrl, headers=newSearchHeaders, timeout=10)
    except requests.RequestException as e:
        return False, f"请求异常：{str(e)}"

    if response.status_code != 200:
        return False, f"请求失败，状态码：{response.status_code}"

    data = response.json()
    if data.get('code') != 0:
        return False, f"接口返回错误：{data.get('message', '未知错误')}"

    resultList = data.get('data', {}).get('result', [])
    videoList = []

    for item in resultList:
        if item.get('result_type') == 'video':
            for video in item.get('data', []):
                videoList.append({
                    'bvid': video.get('bvid'),
                    'title': video.get('title', '').replace('<em class="keyword">', '').replace('</em>', ''),
                    'author': video.get('author', video.get('upname', video.get('name', '未知作者')))
                })

    return videoList


def bilibiliSearch(keyword: str, useOldApi: bool = False):
    """
    搜索 B 站视频（根据 useOldApi 选择新旧接口）

    Args:
        keyword: 搜索关键词

    Returns:
        list: 搜索结果列表，每个元素包含 {bvid, title, author}

    Raises:
        False: 请求失败时返回 False 并包含错误信息
    """
    if useOldApi:
        return bilibiliSearchOld(keyword)
    else:
        return bilibiliSearchNew(keyword)


def getFile(bvid: str):
    """
    根据 BVID 下载视频中的音频，保存为 music.mp3 并自动播放

    Args:
        bvid: 视频的 BVID
    """

    # 1. 获取视频的 cid
    pageUrl = f"https://api.bilibili.com/x/player/pagelist?bvid={bvid}"
    responsePage = requests.get(pageUrl, headers=getFileHeaders)
    pageData = responsePage.json()
    cid = pageData['data'][0]['cid']
    print(f"CID: {cid}")

    # 2. 获取音频播放地址
    playUrl = f"https://api.bilibili.com/x/player/playurl?fnval=80&cid={cid}&bvid={bvid}"
    headersPlay = {
        'referer': 'https://www.bilibili.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:102.0) Gecko/20100101 Firefox/102.0',
    }
    responsePlay = requests.get(playUrl, headers=headersPlay)
    playData = responsePlay.json()
    # 取最后一个音频的备用地址（索引1）
    audioItem = playData['data']['dash']['audio'][-1]
    audioUrl = audioItem["backup_url"][1]  # 与原始逻辑一致

    # 3. 下载音频文件
    try:
        responseAudio = requests.get(audioUrl, headers=headersPlay)
        if responseAudio.status_code == 200:
            responseFile = responseAudio.content
            return True,responseFile
        else:
            return False,f"请求失败，状态码: {responseAudio.status_code}"
    except requests.RequestException as e:
        return False,f"请求出现异常: {str(e)}"
