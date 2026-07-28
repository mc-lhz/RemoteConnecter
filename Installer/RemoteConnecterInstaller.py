import sys
import os
import subprocess
import requests
import shutil
import tkinter as tk
from tkinter import messagebox
import tkinter.ttk as ttk
import tempfile
import threading
from urllib.parse import urlparse
import psutil

updaterFileName = "RemoteConnecter.exe"
downloadLink = "https://gitee.com/mc_lhz/file-storage/releases/download/v1.3.2/RemoteConnecter.exe"
def isPackaged():
    """是否在 PyInstaller 打包环境中运行"""
    return hasattr(sys, '_MEIPASS') or getattr(sys, 'frozen', False)
def getIP():
    """获取本地IP地址"""
    import requests
    ipList = [
        addr.address
        for interface, addrs in psutil.net_if_addrs().items()
        for addr in addrs
        if addr.family.name == 'AF_INET'
    ]
    return '\n'.join(ipList)
def getFilenameFromHeader(response):
    """从响应头获取文件名"""
    cd = response.headers.get('Content-Disposition')
    if cd:
        import re
        match = re.search(r'filename="?([^"]+)"?', cd)
        if match:
            return match.group(1)
    return None


def remoteDownload(url, saveDir, progressCallback=None):
    """
    下载文件并实时更新进度条

    Args:
        url: 下载地址
        saveDir: 保存目录
        progressCallback: 进度回调函数(percent: int)

    Returns:
        (success: bool, savePath or error: str)
    """
    response = requests.get(url, timeout=30, stream=True, verify=False, proxies={'http': None, 'https': None})
    response.raise_for_status()

    fileName = getFilenameFromHeader(response)
    if not fileName:
        fileName = os.path.basename(urlparse(url).path) or 'RemoteConnecter.exe'

    savePath = os.path.join(saveDir, fileName)
    totalSize = int(response.headers.get('Content-Length', 0))
    downloaded = 0
    chunkSize = 1024 * 1024  # 1MB

    try:
        with open(savePath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunkSize):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if totalSize > 0 and progressCallback:
                        percent = int(downloaded / totalSize * 100)
                        progressCallback(percent)
        if progressCallback:
            progressCallback(100)
        return True, savePath
    except Exception as e:
        return False, str(e)

def installRemoteConnecter(method: str):
    """安装 RemoteConnecter（线程版）"""
    # 禁用按钮，防止重复点击
    installButton.config(state='disabled')
    downloadProgressBar['value'] = 0
    downloadProgressBar['maximum'] = 100
    downloadProgressBar.config(mode='determinate')

    def downloadTask():
        temp_dir = tempfile.gettempdir()

        def updateProgress(percent):
            # 通过 after 在主线程中更新进度条
            root.after(0, lambda: downloadProgressBar.config(value=percent))

        success, result = remoteDownload(
            downloadLink,
            temp_dir,
            progressCallback=updateProgress
        )

        # 下载完成后，回到主线程处理安装
        root.after(0, lambda: onDownloadFinished(success, result, method))

    def onDownloadFinished(success, result, method):
        """下载完成后的处理（主线程执行）"""
        installButton.config(state='normal')
        if not success:
            messagebox.showerror("下载失败", f"下载失败：{result}")
            return

        download_path = result
        if isPackaged():
            if method == "sys32":
                installToSys32(download_path)
            elif method == "startup":
                installToStartup(download_path)
            else:
                print("未知安装方法")
        else:
            messagebox.showinfo("未打包，仅下载到临时目录：", download_path)

    # 启动子线程
    threading.Thread(target=downloadTask, daemon=True).start()

def installToSys32(updaterPath: str):
    """
    安装到system32目录
    """
    global updaterFileName
    windowsRoot = os.environ.get('SystemRoot', r'C:\Windows')
    system32Root = os.path.join(windowsRoot, 'System32')
    targetFilePath = os.path.join(system32Root, updaterFileName)

    shutil.copy(updaterPath, targetFilePath)
    regCommand = rf'reg add "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run" /v RemoteConnecter /t REG_SZ /d "{targetFilePath}" /f'
    subprocess.run(regCommand, shell=True, check=True, timeout=10)
    subprocess.Popen(targetFilePath, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
    messagebox.showinfo("安装成功", f"已将 {updaterFileName} 安装到system32目录")

def installToStartup(updaterPath: str):
    """
    安装到启动项
    """
    global updaterFileName
    commonStartupDir = os.path.join(
    os.environ.get('ProgramData', r'C:\ProgramData'),
    r'Microsoft\Windows\Start Menu\Programs\StartUp'
)
    targetFilePath = os.path.join(commonStartupDir, updaterFileName)
    shutil.copy(updaterPath, targetFilePath)
    subprocess.Popen(targetFilePath, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
    messagebox.showinfo("安装成功", f"已将 {updaterFileName} 安装到启动项")
    
    
if __name__ == "__main__":
    
    root = tk.Tk()
    root.title("RemoteConnecter Installer")
    root.geometry("400x300")
    selectMethodComboBox = ttk.Combobox(root, values=["sys32", "startup"])

    selectMethodComboBox.place(x=10, y=10)
    selectMethodComboBox.current(0)

    installButton = ttk.Button(root, text="Install", command=lambda: installRemoteConnecter(selectMethodComboBox.get()))
    installButton.place(x=10, y=40)

    downloadProgressBar = ttk.Progressbar(root, orient="horizontal", length=300, mode="determinate")
    downloadProgressBar.place(x=10, y=70)
    ipLabel = ttk.Label(root, text="IP地址: " + " ".join(getIP()))
    ipLabel.place(x=10, y=100)



    if "-nogui" in sys.argv or "/nogui" in sys.argv:
        if "sys32" in sys.argv:
            installRemoteConnecter("sys32")
        elif "startup" in sys.argv:
            installRemoteConnecter("startup")
        else:
            print("未知安装方法")
        
    else:
        root.mainloop()

