# repoUpdate（仓库更新）
import os
import requests
os.chdir(os.path.dirname(os.path.abspath(__file__)))
NODE_POOL = [
    "https://gh.dpik.top",
    "https://github.dpik.top",
    "https://gh-proxy.com",
    "https://github.tbap.top",
    "https://github.starrlzy.cn",
    "https://github-proxy.memory-echoes.cn",
    "https://j.1win.ggff.net",
    "https://ghproxy.net",
    "https://tvv.tw",
    "https://gh.inkchills.cn",
    "https://gitproxy.127731.xyz",
    "https://jiashu.1win.eu.org",
    "https://gh.acmsz.top",
    "https://ghpr.cc",
    "https://gitproxy.mrhjx.cn",
    "https://github.chenc.dev",
]

'''
示例：
[
    {
        "address": "https://gh.dpik.top",
        "speed": 0.5
    },
    {
        "address": "https://github.dpik.top",
        "speed": 0.5
    },
    ...
    {
        "address": "https://gh-proxy.com",
        "speed": 0.5
    },
]
'''


def speedTest():
    availableNodes = []
    """测试节点速度"""
    for node in NODE_POOL:
        try:
            response = requests.get(node, timeout=0.5)
            print(f"{node} 速度正常，速度：{response.elapsed.total_seconds()}秒")
            # 插入列表
            availableNodes.append({"address": node, "speed": response.elapsed.total_seconds()})
            if response.elapsed.total_seconds() < 0.5:
                break
        except requests.exceptions.RequestException:
            print(f"{node} 速度异常")
    # 按速度排序
    availableNodes.sort(key=lambda x: x["speed"])
    return availableNodes
def getRelease():
    """获取发行版"""
    repoPath = "mc-lhz/RemoteConnecter"
    # 尝试直连获取
    baseAPI = f"https://api.github.com/repos/{repoPath}/releases/latest"
    response = requests.get(baseAPI, verify=False)
    if response.status_code != 200:
        # 从私有化CloudFlare Workers获取
        print(f"获取发行版失败，状态码：{response.status_code}")
        print("尝试从私有化CloudFlare Workers获取...")
        baseAPI = f"https://mfygslthnf2gq5lcfzrw63i.mc-lhz.de5.net/repos/{repoPath}/releases/latest"
        response = requests.get(baseAPI, verify=False)
    
    return response.json()
def downloadUpdater():
    """
    下载更新
    """
    releaseUrl = "https://github.com/mc-lhz/RemoteConnecter/releases/latest/download/RemoteConnecter.exe"
    for node in availableNodes:
        nodeAddress = node["address"]
        # 使用最快节点下载
        nodeAddress = node["address"]
        response = requests.get(f"{nodeAddress}/{releaseUrl}", verify=False)
        with open("RemoteConnecter.exe", "wb") as f:
            # 检测MZ头
            if response.content.startswith(b"MZ"):
                f.write(response.content)
                print(f"{nodeAddress} 下载成功")
                break
            else:
                print(f"{nodeAddress} MZ头检测失败")
                
    else:
        print("所有节点下载失败")
        
if __name__ == '__main__':
    availableNodes = speedTest()
    release = getRelease()
    downloadUpdater()
