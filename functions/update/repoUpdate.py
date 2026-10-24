# repoUpdate（仓库更新：从 GitHub Release 经加速节点下载新版 exe）
import os

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_PATH = "mc-lhz/RemoteConnecter"
ASSET_NAME = "RemoteConnecter.exe"
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


def speedTest(timeout=2.0):
    """测试节点速度，返回按耗时升序的可用节点列表 [{address, speed}]。"""
    availableNodes = []
    for node in NODE_POOL:
        try:
            response = requests.get(node, timeout=timeout, verify=False)
            speed = response.elapsed.total_seconds()
            print(f"{node} 速度正常，耗时：{speed}秒")
            availableNodes.append({"address": node, "speed": speed})
        except requests.exceptions.RequestException:
            print(f"{node} 速度异常")
    availableNodes.sort(key=lambda x: x["speed"])
    return availableNodes


def getRelease(timeout=10.0):
    """获取最新发行版信息，直连失败时回退私有化 CloudFlare Workers。"""
    apiUrls = [
        f"https://api.github.com/repos/{REPO_PATH}/releases/latest",
        f"https://mfygslthnf2gq5lcfzrw63i.mc-lhz.de5.net/repos/{REPO_PATH}/releases/latest",
    ]
    for apiUrl in apiUrls:
        try:
            response = requests.get(apiUrl, timeout=timeout, verify=False)
        except requests.exceptions.RequestException as exc:
            print(f"获取发行版网络异常：{exc}")
            continue
        if response.status_code == 200:
            return response.json()
        print(f"获取发行版失败（{apiUrl}），状态码：{response.status_code}")
    raise RuntimeError("所有发行版数据源均不可用")


def assetDownloadUrl(release):
    """从 release 信息中取目标资产下载地址，取不到时回退固定 latest 地址。"""
    for asset in (release or {}).get("assets", []):
        if asset.get("name") == ASSET_NAME and asset.get("browser_download_url"):
            return asset["browser_download_url"]
    return f"https://github.com/{REPO_PATH}/releases/latest/download/{ASSET_NAME}"


def downloadUpdater(availableNodes, release=None, timeout=60.0):
    """经加速节点逐个尝试下载更新，成功返回 True。"""
    if not availableNodes:
        print("没有可用节点")
        return False
    releaseUrl = assetDownloadUrl(release)
    targetPath = os.path.join(SCRIPT_DIR, ASSET_NAME)
    tempPath = targetPath + ".downloading"

    for node in availableNodes:
        nodeAddress = node["address"]
        try:
            response = requests.get(
                f"{nodeAddress}/{releaseUrl}",
                timeout=timeout,
                verify=False,
                stream=True,
            )
        except requests.exceptions.RequestException as exc:
            print(f"{nodeAddress} 下载异常：{exc}")
            continue
        try:
            first = next(response.iter_content(chunk_size=1024 * 1024), b"")
            if not first.startswith(b"MZ"):
                print(f"{nodeAddress} MZ头检测失败")
                continue
            with open(tempPath, "wb") as f:
                f.write(first)
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
            os.replace(tempPath, targetPath)
            print(f"{nodeAddress} 下载成功：{targetPath}")
            return True
        except (requests.exceptions.RequestException, OSError) as exc:
            print(f"{nodeAddress} 下载中断：{exc}")
            continue
        finally:
            response.close()
    if os.path.exists(tempPath):
        try:
            os.remove(tempPath)
        except OSError:
            pass
    print("所有节点下载失败")
    return False


if __name__ == '__main__':
    nodes = speedTest()
    release = getRelease()
    tag = release.get("tag_name", "?")
    print(f"最新发行版：{tag}")
    raise SystemExit(0 if downloadUpdater(nodes, release) else 1)
