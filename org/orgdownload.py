import os
import time
import httpx
import requests
from tqdm import tqdm
from threading import Thread

def url_get(url):
    try:
        res = requests.get(url,timeout=5,allow_redirects=True)
        return res.status_code < 400
    except requests.Timeout:
        return False
    except (requests.ConnectionError, requests.Timeout,requests.TooManyRedirects):
        return False


import os
import sys
import threading
import requests
from pathlib import Path
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import urllib3

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class MultiThreadDownloader:
    """多线程下载器类，支持断点续传和进度显示"""

    def __init__(self, url: str, save_path: str, thread_count: int = 8,
                 chunk_size: int = 1024 * 1024):
        """
        初始化下载器

        Args:
            url: 下载文件的URL
            save_path: 保存文件的路径
            thread_count: 线程数量，默认8个
            chunk_size: 每个分块的大小（字节），默认1MB
        """
        self.url = url
        self.save_path = save_path
        self.thread_count = thread_count
        self.chunk_size = chunk_size
        self.temp_dir = f"{save_path}.download"
        self.progress_file = f"{save_path}.progress"

        # 下载状态
        self.total_size = 0
        self.downloaded_size = 0
        self.lock = threading.Lock()
        self.is_downloading = False

    def get_file_size(self) -> int:
        """获取远程文件大小"""
        try:
            response = requests.head(self.url, allow_redirects=True, timeout=10, verify=False)
            if 'Content-Length' in response.headers:
                return int(response.headers['Content-Length'])
            else:
                # 如果HEAD请求不返回Content-Length，尝试GET请求
                response = requests.get(self.url, stream=True, timeout=10, verify=False)
                if 'Content-Length' in response.headers:
                    return int(response.headers['Content-Length'])
                else:
                    raise Exception("无法获取文件大小，服务器不支持Range请求")
        except Exception as e:
            raise Exception(f"获取文件大小失败: {str(e)}")

    def check_support_range(self) -> bool:
        """检查服务器是否支持Range请求（断点续传）"""
        try:
            headers = {'Range': 'bytes=0-0'}
            response = requests.head(self.url, headers=headers, allow_redirects=True, timeout=10, verify=False)
            return response.status_code == 206 or 'Accept-Ranges' in response.headers
        except:
            return False

    def download_chunk(self, start: int, end: int, chunk_id: int) -> bool:
        """
        下载文件的一个分块

        Args:
            start: 起始字节位置
            end: 结束字节位置
            chunk_id: 分块ID

        Returns:
            是否下载成功
        """
        chunk_file = os.path.join(self.temp_dir, f"chunk_{chunk_id}.tmp")

        # 检查是否已经下载过该分块
        if os.path.exists(chunk_file):
            downloaded = os.path.getsize(chunk_file)
            if downloaded == (end - start + 1):
                with self.lock:
                    self.downloaded_size += downloaded
                return True
            else:
                # 部分下载，继续从断点处下载
                start += downloaded
                with self.lock:
                    self.downloaded_size += downloaded

        headers = {'Range': f'bytes={start}-{end}'}

        try:
            response = requests.get(self.url, headers=headers, stream=True, timeout=30, verify=False)

            if response.status_code not in [200, 206]:
                return False

            with open(chunk_file, 'ab') as f:
                for data in response.iter_content(chunk_size=8192):
                    if not self.is_downloading:
                        return False

                    if data:
                        f.write(data)
                        with self.lock:
                            self.downloaded_size += len(data)

            return True

        except Exception as e:
            print(f"\n分块 {chunk_id} 下载失败: {str(e)}")
            return False

    def merge_chunks(self, chunk_count: int) -> bool:
        """
        合并所有下载的分块

        Args:
            chunk_count: 分块数量

        Returns:
            是否合并成功
        """
        try:
            with open(self.save_path, 'wb') as output_file:
                for i in range(chunk_count):
                    chunk_file = os.path.join(self.temp_dir, f"chunk_{i}.tmp")
                    if not os.path.exists(chunk_file):
                        return False

                    with open(chunk_file, 'rb') as chunk:
                        output_file.write(chunk.read())

            return True
        except Exception as e:
            print(f"\n合并文件失败: {str(e)}")
            return False

    def cleanup(self):
        """清理临时文件"""
        try:
            if os.path.exists(self.temp_dir):
                for file in os.listdir(self.temp_dir):
                    os.remove(os.path.join(self.temp_dir, file))
                os.rmdir(self.temp_dir)

            if os.path.exists(self.progress_file):
                os.remove(self.progress_file)
        except Exception as e:
            print(f"\n清理临时文件失败: {str(e)}")

    def show_progress(self):
        """显示下载进度条"""
        while self.is_downloading:
            if self.total_size > 0:
                progress = self.downloaded_size / self.total_size
                bar_length = 50
                filled_length = int(bar_length * progress)
                bar = '█' * filled_length + '░' * (bar_length - filled_length)

                # 计算下载速度
                percent = progress * 100
                downloaded_mb = self.downloaded_size / (1024 * 1024)
                total_mb = self.total_size / (1024 * 1024)

                sys.stdout.write(f'\r下载进度: |{bar}| {percent:.1f}% '
                                 f'({downloaded_mb:.2f}MB / {total_mb:.2f}MB)')
                sys.stdout.flush()

            time.sleep(0.1)

    def download(self, resume: bool = True) -> bool:
        """
        开始下载文件

        Args:
            resume: 是否启用断点续传，默认True

        Returns:
            是否下载成功
        """
        try:
            # 检查文件是否已存在
            if os.path.exists(self.save_path) and not resume:
                print(f"文件已存在: {self.save_path}")
                return True

            # 获取文件大小
            print("正在获取文件信息...")
            self.total_size = self.get_file_size()
            print(f"文件大小: {self.total_size / (1024 * 1024):.2f} MB")

            # 检查是否支持断点续传
            support_range = self.check_support_range()
            if not support_range:
                print("警告: 服务器不支持断点续传，将使用单线程下载")
                self.thread_count = 1
            else:
                print(f"服务器支持断点续传，使用 {self.thread_count} 个线程下载")

            # 创建临时目录
            os.makedirs(self.temp_dir, exist_ok=True)

            # 计算每个线程下载的范围
            chunk_size = self.total_size // self.thread_count
            download_ranges = []

            for i in range(self.thread_count):
                start = i * chunk_size
                end = start + chunk_size - 1 if i < self.thread_count - 1 else self.total_size - 1
                download_ranges.append((start, end, i))

            # 开始下载
            self.is_downloading = True

            # 启动进度显示线程
            progress_thread = threading.Thread(target=self.show_progress, daemon=True)
            progress_thread.start()

            # 使用线程池下载
            success = True
            with ThreadPoolExecutor(max_workers=self.thread_count) as executor:
                futures = {
                    executor.submit(self.download_chunk, start, end, chunk_id): chunk_id
                    for start, end, chunk_id in download_ranges
                }

                for future in as_completed(futures):
                    if not future.result():
                        success = False
                        break

            self.is_downloading = False
            progress_thread.join(timeout=1)

            if not success:
                print("\n下载失败！")
                return False

            # 确保进度条显示100%
            sys.stdout.write(f'\r下载进度: |{"█" * 50}| 100.0% '
                             f'({self.total_size / (1024 * 1024):.2f}MB / {self.total_size / (1024 * 1024):.2f}MB)\n')
            sys.stdout.flush()

            # 合并文件
            print("正在合并文件...")
            if not self.merge_chunks(self.thread_count):
                print("合并文件失败！")
                return False

            # 清理临时文件
            print("正在清理临时文件...")
            self.cleanup()

            print(f"下载完成！文件保存至: {self.save_path}")
            return True

        except KeyboardInterrupt:
            print("\n\n下载已暂停，临时文件已保存，下次可以继续下载")
            self.is_downloading = False
            return False
        except Exception as e:
            print(f"\n下载出错: {str(e)}")
            self.is_downloading = False
            return False


def download_file(url: str, save_path: str) -> bool:
    """
    便捷的下载函数接口

    Args:
        url: 下载文件的URL
        save_path: 保存文件的路径

    Returns:
        是否下载成功

    Example:
        >>> download_file("https://example.com/large_file.zip", "./file.zip")
    """
    downloader = MultiThreadDownloader(url, save_path, thread_count=8)
    return downloader.download(resume=True)


if __name__ == "__main__":
    # 示例用法
    if len(sys.argv) < 3:
        print("用法: python multi_thread_downloader.py <URL> <保存路径> [线程数]")
        print("示例: python multi_thread_downloader.py https://example.com/file.zip ./file.zip 8")
        sys.exit(1)

    url = sys.argv[1]
    save_path = sys.argv[2]
    thread_count = int(sys.argv[3]) if len(sys.argv) > 3 else 8

    success = download_file(url, save_path)
    sys.exit(0 if success else 1)
"""def main(url1,url2,data_folder,thread_num):
    urls = [url1, url2]
    for i, url in enumerate(urls,start=1):
        if url_get(i) == True:
            text_1 = "链接测试已通过 开始尝试拉取文件"
            downloader = DownloadFile(i, data_folder, thread_num)
            downloader.main()
        break
"""