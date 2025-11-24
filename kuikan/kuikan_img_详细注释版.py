# -*- coding: utf-8 -*-
"""
KuaikanClient All-in-One
- 登录（本地 Cookie 注入）
- 获取章节（核心方式按用户给定版本，不随意改动）
- 选择性筛选章节
- 单话图片直链提取（解析 DOM）
- 多线程下载到：E:/kuaikan/漫画标题/001 第1话 XXX/001.JPG（JPEG质量100%）
"""

import os  # 执行语句（保持原逻辑不变）
import re  # 执行语句（保持原逻辑不变）
import io  # 执行语句（保持原逻辑不变）
import json  # 执行语句（保持原逻辑不变）
import time  # 执行语句（保持原逻辑不变）
import html as _html  # 执行语句（保持原逻辑不变）
import logging  # 执行语句（保持原逻辑不变）
import threading  # 执行语句（保持原逻辑不变）
from typing import List, Tuple, Dict, Any, Optional, Iterable  # 执行语句（保持原逻辑不变）
from urllib.parse import urlparse  # 执行语句（保持原逻辑不变）
from concurrent.futures import ThreadPoolExecutor, as_completed  # 创建线程池以并发下载多个图片

import requests  # 执行语句（保持原逻辑不变）
from PIL import Image  # 执行语句（保持原逻辑不变）

from selenium import webdriver  # 执行语句（保持原逻辑不变）
from selenium.webdriver.chrome.service import Service  # 执行语句（保持原逻辑不变）
from selenium.webdriver.chrome.options import Options  # 执行语句（保持原逻辑不变）
from selenium.webdriver.common.by import By  # 执行语句（保持原逻辑不变）
from selenium.webdriver.support.ui import WebDriverWait  # 执行语句（保持原逻辑不变）
from selenium.webdriver.support import expected_conditions as EC  # 执行语句（保持原逻辑不变）


# ========================== 日志工具 ==========================
def setup_logger(log_file: Optional[str] = None, level=logging.INFO):  # 日志文件路径（None 表示只输出到控制台）
    fmt = "%(asctime)s [%(levelname)s] - %(message)s"  # 执行语句（保持原逻辑不变）
    datefmt = "%H:%M:%S"  # 执行语句（保持原逻辑不变）
    logger = logging.getLogger("kuaikan")  # 执行语句（保持原逻辑不变）
    logger.setLevel(level)  # 执行语句（保持原逻辑不变）
    logger.handlers.clear()  # 执行语句（保持原逻辑不变）

    sh = logging.StreamHandler()  # 执行语句（保持原逻辑不变）
    sh.setLevel(level)  # 执行语句（保持原逻辑不变）
    sh.setFormatter(logging.Formatter(fmt, datefmt=datefmt))  # 执行语句（保持原逻辑不变）
    logger.addHandler(sh)  # 执行语句（保持原逻辑不变）

    if log_file:  # 日志文件路径（None 表示只输出到控制台）
        fh = logging.FileHandler(log_file, encoding="utf-8")  # 日志文件路径（None 表示只输出到控制台）
        fh.setLevel(level)  # 执行语句（保持原逻辑不变）
        fh.setFormatter(logging.Formatter(fmt, datefmt=datefmt))  # 执行语句（保持原逻辑不变）
        logger.addHandler(fh)  # 执行语句（保持原逻辑不变）
    return logger  # 返回函数执行结果


# ========================== 主类 ==========================
class KuaikanClient:  # 定义类
    """
    快看漫画客户端（封装：登录 / 章节抓取 / 选择过滤 / 图片解析 / 多线程下载）
    - 章节抓取核心方式与用户提供版本一致（NUXT -> API -> DOM）
    """

    def __init__(  # 定义函数
        self,  # 执行语句（保持原逻辑不变）
        chrome_binary_path: str,  # Chrome 浏览器可执行文件路径，用于启动浏览器
        chromedriver_path: str,  # ChromeDriver 驱动路径，用于 Selenium 控制浏览器
        cookie_json_path: str,  # 保存登录 Cookie 的 JSON 文件路径
        save_root: str = r"E:/kuaikan",  # 漫画图片保存的根目录路径
        max_workers: int = 8,  # 下载图片时线程池的最大并发线程数
        jpg_quality: int = 100,  # 保存图片的 JPEG 质量（范围 0-100）
        retries: int = 3,  # 下载失败后的最大重试次数
        timeout: int = 20,  # 网络请求或等待的超时时间（秒）
        headless: bool = False,  # 是否启用无头模式（隐藏浏览器界面）
        log_file: Optional[str] = None,  # 日志文件路径（None 表示只输出到控制台）
    ):  # 执行语句（保持原逻辑不变）
        self.chrome_binary_path = chrome_binary_path  # Chrome 浏览器可执行文件路径，用于启动浏览器
        self.chromedriver_path = chromedriver_path  # ChromeDriver 驱动路径，用于 Selenium 控制浏览器
        self.cookie_json_path = cookie_json_path  # 保存登录 Cookie 的 JSON 文件路径

        self.save_root = save_root  # 漫画图片保存的根目录路径
        self.max_workers = max_workers  # 下载图片时线程池的最大并发线程数
        self.jpg_quality = jpg_quality  # 保存图片的 JPEG 质量（范围 0-100）
        self.retries = retries  # 下载失败后的最大重试次数
        self.timeout = timeout  # 网络请求或等待的超时时间（秒）
        self.headless = headless  # 是否启用无头模式（隐藏浏览器界面）

        os.makedirs(self.save_root, exist_ok=True)  # 漫画图片保存的根目录路径

        self.log = setup_logger(log_file)  # 日志文件路径（None 表示只输出到控制台）
        self.log.info("初始化 KuaikanClient 参数：save_root=%s | workers=%d | jpg=%d | retries=%d | timeout=%ds | headless=%s",  # 漫画图片保存的根目录路径
                      self.save_root, self.max_workers, self.jpg_quality, self.retries, self.timeout, self.headless)  # 漫画图片保存的根目录路径

        self.driver: Optional[webdriver.Chrome] = None  # 执行语句（保持原逻辑不变）
        self._lock = threading.Lock()  # 执行语句（保持原逻辑不变）

    # -------------------------- 登录 --------------------------
    def login(self, topic_url: str, base_url: str = "https://www.kuaikanmanhua.com"  # 定义函数
              ) -> Tuple[bool, str, str, webdriver.Chrome]:  # 执行语句（保持原逻辑不变）
        """
        注入本地 Cookie 并打开专题页
        :return: (ok, msg, title, driver)
        """
        self.log.info("开始登录：注入 Cookie -> %s", self.cookie_json_path)  # 保存登录 Cookie 的 JSON 文件路径
        self.driver = self._build_driver(self.chrome_binary_path, self.chromedriver_path, self.headless)  # Chrome 浏览器可执行文件路径，用于启动浏览器

        self.driver.get(base_url)  # 执行语句（保持原逻辑不变）
        time.sleep(1.0)  # 暂停指定秒数，用于等待页面加载

        cookies = self._load_cookies_from_file(self.cookie_json_path)  # 保存登录 Cookie 的 JSON 文件路径
        added = 0  # 执行语句（保持原逻辑不变）
        for c in cookies:  # 循环遍历序列或集合
            addable = {"name": c.get("name"), "value": c.get("value")}  # 执行语句（保持原逻辑不变）
            if not addable["name"]:  # 条件判断语句
                continue  # 执行语句（保持原逻辑不变）
            if c.get("domain"):  # 条件判断语句
                addable["domain"] = c["domain"]  # 执行语句（保持原逻辑不变）
            if c.get("path"):  # 条件判断语句
                addable["path"] = c["path"]  # 执行语句（保持原逻辑不变）
            if c.get("expiry"):  # 条件判断语句
                try:  # 异常捕获块开始
                    addable["expiry"] = int(c["expiry"])  # 执行语句（保持原逻辑不变）
                except Exception:  # 捕获异常并处理错误
                    pass  # 执行语句（保持原逻辑不变）
            if "secure" in c:  # 条件判断语句
                addable["secure"] = bool(c["secure"])  # 执行语句（保持原逻辑不变）
            if "httpOnly" in c:  # 条件判断语句
                addable["httpOnly"] = bool(c["httpOnly"])  # 执行语句（保持原逻辑不变）
            try:  # 异常捕获块开始
                self.driver.add_cookie(addable)  # 执行语句（保持原逻辑不变）
                added += 1  # 执行语句（保持原逻辑不变）
            except Exception:  # 捕获异常并处理错误
                pass  # 执行语句（保持原逻辑不变）
        self.log.info("已注入 Cookie 条数：%d", added)  # 输出普通信息日志

        self.driver.get(topic_url)  # 执行语句（保持原逻辑不变）
        try:  # 异常捕获块开始
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))  # 等待页面元素加载完成
        except Exception:  # 捕获异常并处理错误
            pass  # 执行语句（保持原逻辑不变）
        time.sleep(1.0)  # 暂停指定秒数，用于等待页面加载

        title = self.driver.title or ""  # 获取网页标签的标题文本
        ok = self._check_login_status()  # 执行语句（保持原逻辑不变）
        msg = "注入成功，登录成功" if ok else "Cookie 注入完成，但未检测到登录态"  # 执行语句（保持原逻辑不变）
        self.log.info("[登录] %s | 页面标题：%s", msg, title)  # 输出普通信息日志
        return ok, msg, title, self.driver  # 漫画标题或章节标题

    def _check_login_status(self) -> bool:  # 定义函数
        ok = False  # 执行语句（保持原逻辑不变）
        try:  # 异常捕获块开始
            no_user = self.driver.find_elements(By.CSS_SELECTOR, ".User .noUser")  # 使用 Selenium 定位页面元素
            if not no_user:  # 条件判断语句
                ok = True  # 执行语句（保持原逻辑不变）
            txt = self.driver.page_source  # 执行语句（保持原逻辑不变）
            if ("登录" in txt or "注册" in txt) and no_user:  # 条件判断语句
                ok = False  # 执行语句（保持原逻辑不变）
            site_cookies = self.driver.get_cookies()  # 执行语句（保持原逻辑不变）
            names = " ".join([c["name"].lower() for c in site_cookies if "name" in c])  # 执行语句（保持原逻辑不变）
            if any(k in names for k in ["token", "uid", "session", "auth"]):  # 条件判断语句
                ok = True  # 执行语句（保持原逻辑不变）
        except Exception:  # 捕获异常并处理错误
            pass  # 执行语句（保持原逻辑不变）
        return ok  # 返回函数执行结果

    # -------------------------- 章节抓取（核心方式保持不变） --------------------------
    def fetch_chapters(self, topic_url: str, limit: int = 60  # 定义函数
                       ) -> Tuple[str, List[Dict[str, Any]]]:  # 执行语句（保持原逻辑不变）
        """
        章节字段：order、episode_no、title、url、id
        逻辑：NUXT -> API -> DOM（与你提供的版本一致，尽量不改动）
        """
        # ==== 新增：用页面信息区替换/净化标题 ====

        #取标题
        page_title   = self.driver.find_element(By.CSS_SELECTOR, ".right .title").text.strip()  # 使用 Selenium 定位页面元素
        #取作者
        page_author = self.driver.find_element(By.CSS_SELECTOR, ".right .nickname").text.strip()  # 使用 Selenium 定位页面元素
        #取简介
        page_ntro = self.driver.find_element(By.CSS_SELECTOR, ".comicIntro .detailsBox p").text.strip()  # 使用 Selenium 定位页面元素

        if not self.driver:  # 条件判断语句
            raise RuntimeError("请先调用 login() 完成登录。")  # 执行语句（保持原逻辑不变）

        self.log.info("[章节] 尝试从 NUXT 状态读取")  # 输出普通信息日志
        items = self._try_fetch_from_nuxt_state(self.driver)  # 执行语句（保持原逻辑不变）
        for i, ch in enumerate(items, 1):  # 循环遍历序列或集合
            ch["order"] = i  # 执行语句（保持原逻辑不变）
            ch["url"] = self._build_comic_url(str(ch.get("id")))  # 存放网页或图片的链接 URL
        self.log.info("[章节] 获取完成：共 %d 条", len(items))  # 输出普通信息日志
        return page_title, items  # 漫画标题或章节标题

    
    # -------------------------- 选择性下载（筛选） --------------------------
    @staticmethod  # 执行语句（保持原逻辑不变）
    def parse_select_spec(spec: str) -> List[Tuple[int, int]]:  # 定义函数
        """
        解析选择串：如 "1-3,6,8-10" -> [(1,3),(6,6),(8,10)]
        """
        out = []  # 执行语句（保持原逻辑不变）
        if not spec:  # 条件判断语句
            return out  # 返回函数执行结果
        for part in spec.split(","):  # 循环遍历序列或集合
            part = part.strip()  # 执行语句（保持原逻辑不变）
            if not part:  # 条件判断语句
                continue  # 执行语句（保持原逻辑不变）
            if "-" in part:  # 条件判断语句
                a, b = part.split("-", 1)  # 执行语句（保持原逻辑不变）
                try:  # 异常捕获块开始
                    a, b = int(a), int(b)  # 执行语句（保持原逻辑不变）
                    if a > b:  # 条件判断语句
                        a, b = b, a  # 执行语句（保持原逻辑不变）
                    out.append((a, b))  # 执行语句（保持原逻辑不变）
                except Exception:  # 捕获异常并处理错误
                    continue  # 执行语句（保持原逻辑不变）
            else:  # 执行语句（保持原逻辑不变）
                try:  # 异常捕获块开始
                    n = int(part)  # 执行语句（保持原逻辑不变）
                    out.append((n, n))  # 执行语句（保持原逻辑不变）
                except Exception:  # 捕获异常并处理错误
                    continue  # 执行语句（保持原逻辑不变）
        return out  # 返回函数执行结果

    @staticmethod  # 执行语句（保持原逻辑不变）
    def filter_by_ranges(chapters: List[Dict[str, Any]], ranges: List[Tuple[int, int]]) -> List[Dict[str, Any]]:  # 定义函数
        if not ranges:  # 条件判断语句
            return chapters  # 返回函数执行结果
        def hit(n: int):  # 定义函数
            return any(a <= n <= b for a, b in ranges)  # 返回函数执行结果
        return [c for c in chapters if hit(c.get("order", 0))]  # 返回函数执行结果

    # -------------------------- 单话图片提取（DOM 解析） --------------------------
    def fetch_comic_images_by_parsing(self, chapter_url: str, max_scroll: int = 10, wait_sec: float = 0.6) -> List[str]:  # 定义函数
        """
        用 Selenium 打开章节页，滚动触发懒加载，抓取 .imgList .img-box img.img 的 data-src/src
        """
        if not self.driver:  # 条件判断语句
            raise RuntimeError("请先调用 login() 完成登录。")  # 执行语句（保持原逻辑不变）
        self.log.info("[图片] 打开章节页：%s", chapter_url)  # 输出普通信息日志
        d = self.driver  # 执行语句（保持原逻辑不变）
        d.get(chapter_url)  # 执行语句（保持原逻辑不变）
        WebDriverWait(d, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".imgList")))  # 等待页面元素加载完成

        last_height = 0  # 执行语句（保持原逻辑不变）
        for i in range(max_scroll):  # 循环遍历序列或集合
            d.execute_script("window.scrollTo(0, document.body.scrollHeight);")  # 执行语句（保持原逻辑不变）
            time.sleep(wait_sec)  # 暂停指定秒数，用于等待页面加载
            new_height = d.execute_script("return document.body.scrollHeight")  # 执行语句（保持原逻辑不变）
            self.log.debug("[图片] 滚动第 %d 次 | 高度=%s", i + 1, new_height)  # 执行语句（保持原逻辑不变）
            if new_height == last_height:  # 条件判断语句
                break  # 执行语句（保持原逻辑不变）
            last_height = new_height  # 执行语句（保持原逻辑不变）

        html_text = d.page_source  # 执行语句（保持原逻辑不变）
        urls = self.parse_img_urls_from_html(html_text)  # 存放网页或图片的链接 URL
        self.log.info("[图片] 共抽取 %d 张", len(urls))  # 输出普通信息日志
        return urls  # 返回函数执行结果

    @staticmethod  # 执行语句（保持原逻辑不变）
    def parse_img_urls_from_html(html_text: str) -> List[str]:  # 定义函数
        """
        解析章节 HTML：只取 .imgList .img-box 里的第一张 img.img 的 data-src/src
        """
        from bs4 import BeautifulSoup  # 执行语句（保持原逻辑不变）
        soup = BeautifulSoup(html_text, "html.parser")  # 使用 BeautifulSoup 解析 HTML 文本
        out, seen = [], set()  # 执行语句（保持原逻辑不变）
        for box in soup.select(".imgList .img-box"):  # 循环遍历序列或集合
            img = box.select_one("img.img")  # 执行语句（保持原逻辑不变）
            if not img:  # 条件判断语句
                continue  # 执行语句（保持原逻辑不变）
            u = img.get("data-src") or img.get("src") or ""  # 获取 img 标签的属性（如 src 或 data-src）
            u = _html.unescape((u or "").strip())  # 执行语句（保持原逻辑不变）
            if not u:  # 条件判断语句
                continue  # 执行语句（保持原逻辑不变）
            if u.startswith("//"):  # 条件判断语句
                u = "https:" + u  # 执行语句（保持原逻辑不变）
            if u not in seen:  # 条件判断语句
                seen.add(u)  # 执行语句（保持原逻辑不变）
                out.append(u)  # 执行语句（保持原逻辑不变）
        return out  # 返回函数执行结果

    # -------------------------- 多线程下载 --------------------------
    def download_chapter(  # 定义函数
        self,  # 执行语句（保持原逻辑不变）
        topic_title: str,  # 漫画标题或章节标题
        chapter: Dict[str, Any],  # 执行语句（保持原逻辑不变）
        referer: Optional[str] = None,  # 执行语句（保持原逻辑不变）
    ) -> None:  # 执行语句（保持原逻辑不变）
        """
        下载单话到：E:/kuaikan/{topic_title}/{001 第1话 XXX}/001.JPG ...
        """
        order = chapter.get("order", 0)  # 执行语句（保持原逻辑不变）
        chap_title = (chapter.get("title") or "").strip().replace("\n", " ")  # 漫画标题或章节标题
        folder_name = f"{order:03d}  {chap_title}".strip()  # 漫画标题或章节标题
        save_dir = os.path.join(self.save_root, self._safe_name(topic_title), self._safe_name(folder_name))  # 漫画图片保存的根目录路径
        os.makedirs(save_dir, exist_ok=True)  # 创建目录（如果不存在）

        chapter_url = chapter.get("url")  # 存放网页或图片的链接 URL
        self.log.info("[下载] 开始：%s -> %s", chapter_url, save_dir)  # 输出普通信息日志

        # 取图片直链
        img_urls = self.fetch_comic_images_by_parsing(chapter_url)  # 存放网页或图片的链接 URL
        if not img_urls:  # 条件判断语句
            self.log.warning("[下载] 未获取到图片：%s", chapter_url)  # 输出警告日志
            return  # 返回函数执行结果

        # 多线程保存
        headers = {  # 执行语句（保持原逻辑不变）
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "  # 执行语句（保持原逻辑不变）
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),  # 执行语句（保持原逻辑不变）
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",  # 执行语句（保持原逻辑不变）
            "Referer": referer or chapter_url,  # 执行语句（保持原逻辑不变）
        }  # 执行语句（保持原逻辑不变）

        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:  # 下载图片时线程池的最大并发线程数
            futures = []  # 执行语句（保持原逻辑不变）
            for idx, u in enumerate(img_urls, 1):  # 循环遍历序列或集合
                out_path = os.path.join(save_dir, f"{idx:03d}.JPG")  # 执行语句（保持原逻辑不变）
                futures.append(ex.submit(self._download_one_image, u, out_path, headers))  # 执行语句（保持原逻辑不变）
            for fut in as_completed(futures):  # 循环遍历序列或集合
                try:  # 异常捕获块开始
                    fut.result()  # 执行语句（保持原逻辑不变）
                except Exception as e:  # 捕获异常并处理错误
                    self.log.error("[下载] 子任务异常：%s", e)  # 输出错误日志

        self.log.info("[下载] 完成：%s | 共 %d 张", folder_name, len(img_urls))  # 输出普通信息日志

    def _download_one_image(self, url: str, out_path: str, headers: Dict[str, str]) -> None:  # 定义函数
        """
        下载单张图片，必要时转存为 JPG（quality=100），含重试。
        """
        if os.path.exists(out_path):  # 检查路径或文件是否存在
            self.log.debug("[跳过] 已存在：%s", out_path)  # 执行语句（保持原逻辑不变）
            return  # 返回函数执行结果

        sess = self._requests_session_from_selenium(self.driver)  # 执行语句（保持原逻辑不变）
        for attempt in range(1, self.retries + 1):  # 下载失败后的最大重试次数
            try:  # 异常捕获块开始
                r = sess.get(url, headers=headers, timeout=self.timeout, stream=True)  # 网络请求或等待的超时时间（秒）
                r.raise_for_status()  # 执行语句（保持原逻辑不变）
                content = r.content  # 执行语句（保持原逻辑不变）

                # 识别格式并转 JPG
                fmt = self._guess_ext_from_url_or_headers(url, r.headers)  # 存放网页或图片的链接 URL
                if fmt in (".jpg", ".jpeg"):  # 条件判断语句
                    with open(out_path, "wb") as f:  # 以二进制写模式保存文件
                        f.write(content)  # 执行语句（保持原逻辑不变）
                else:  # 执行语句（保持原逻辑不变）
                    im = Image.open(io.BytesIO(content)).convert("RGB")  # 执行语句（保持原逻辑不变）
                    im.save(out_path, format="JPEG", quality=self.jpg_quality, optimize=True)  # 保存图片的 JPEG 质量（范围 0-100）

                self.log.debug("[保存] %s <- %s", out_path, url)  # 执行语句（保持原逻辑不变）
                return  # 返回函数执行结果
            except Exception as e:  # 捕获异常并处理错误
                self.log.warning("[重试 %d/%d] 下载失败：%s | %s", attempt, self.retries, url, e)  # 下载失败后的最大重试次数
                time.sleep(0.6)  # 暂停指定秒数，用于等待页面加载
        self.log.error("[失败] 放弃：%s", url)  # 输出错误日志

    @staticmethod  # 执行语句（保持原逻辑不变）
    def _guess_ext_from_url_or_headers(url: str, headers: Dict[str, str]) -> str:  # 定义函数
        path = urlparse(url).path.lower()  # 存放网页或图片的链接 URL
        for ext in (".jpg", ".jpeg", ".png", ".webp"):  # 循环遍历序列或集合
            if path.endswith(ext):  # 条件判断语句
                return ext  # 返回函数执行结果
        ct = headers.get("Content-Type", "").lower()  # 执行语句（保持原逻辑不变）
        if "jpeg" in ct:  # 条件判断语句
            return ".jpg"  # 返回函数执行结果
        if "png" in ct:  # 条件判断语句
            return ".png"  # 返回函数执行结果
        if "webp" in ct:  # 条件判断语句
            return ".webp"  # 返回函数执行结果
        return ".jpg"  # 返回函数执行结果

    # -------------------------- Selenium/requests/工具函数（来自章节代码的实现，尽量不改动，仅加日志） --------------------------
    @staticmethod  # 执行语句（保持原逻辑不变）
    def _build_comic_url(comic_id: str) -> str:  # 定义函数
        return f"https://www.kuaikanmanhua.com/web/comic/{comic_id}"  # 返回函数执行结果

    @staticmethod  # 执行语句（保持原逻辑不变）
    def _load_cookies_from_file(cookie_json_path: str) -> List[Dict[str, Any]]:  # 保存登录 Cookie 的 JSON 文件路径
        with open(cookie_json_path, "r", encoding="utf-8") as f:  # 保存登录 Cookie 的 JSON 文件路径
            data = json.load(f)  # 执行语句（保持原逻辑不变）
        if isinstance(data, dict) and "cookies" in data:  # 条件判断语句
            cookies = data["cookies"]  # 执行语句（保持原逻辑不变）
        elif isinstance(data, list):  # 执行语句（保持原逻辑不变）
            cookies = data  # 执行语句（保持原逻辑不变）
        else:  # 执行语句（保持原逻辑不变）
            raise ValueError("不识别的 cookies JSON 格式，请确认文件内容。")  # 执行语句（保持原逻辑不变）
        if not isinstance(cookies, list):  # 条件判断语句
            raise ValueError("cookies 应为列表。")  # 执行语句（保持原逻辑不变）
        return cookies  # 返回函数执行结果

    def _build_driver(self, chrome_binary_path: str, chromedriver_path: str, headless: bool = False) -> webdriver.Chrome:  # Chrome 浏览器可执行文件路径，用于启动浏览器
        options = Options()  # 执行语句（保持原逻辑不变）
        options.binary_location = chrome_binary_path  # Chrome 浏览器可执行文件路径，用于启动浏览器
        if headless:  # 是否启用无头模式（隐藏浏览器界面）
            options.add_argument("--headless=new")  # 启用 Chrome 无头模式，不显示浏览器窗口
        options.add_argument("--disable-gpu")  # 执行语句（保持原逻辑不变）
        options.add_argument("--no-sandbox")  # 执行语句（保持原逻辑不变）
        options.add_argument("--disable-dev-shm-usage")  # 执行语句（保持原逻辑不变）
        options.add_argument("--window-size=1400,900")  # 执行语句（保持原逻辑不变）
        options.add_experimental_option("excludeSwitches", ["enable-automation"])  # 执行语句（保持原逻辑不变）
        options.add_experimental_option('useAutomationExtension', False)  # 执行语句（保持原逻辑不变）
        options.page_load_strategy = "eager"  # 执行语句（保持原逻辑不变）
        service = Service(executable_path=chromedriver_path)  # ChromeDriver 驱动路径，用于 Selenium 控制浏览器
        driver = webdriver.Chrome(service=service, options=options)  # 执行语句（保持原逻辑不变）
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {  # 执行语句（保持原逻辑不变）
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"  # 执行语句（保持原逻辑不变）
        })  # 执行语句（保持原逻辑不变）
        return driver  # 返回函数执行结果

    @staticmethod  # 执行语句（保持原逻辑不变）
    def _requests_session_from_selenium(driver: webdriver.Chrome) -> requests.Session:  # 定义函数
        s = requests.Session()  # 创建 requests 会话以复用连接与 cookie
        s.headers.update({  # 执行语句（保持原逻辑不变）
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0.0.0 Safari/537.36",  # 执行语句（保持原逻辑不变）
            "Accept": "application/json, text/plain, */*",  # 执行语句（保持原逻辑不变）
            "Referer": "https://www.kuaikanmanhua.com/"  # 执行语句（保持原逻辑不变）
        })  # 执行语句（保持原逻辑不变）
        for c in driver.get_cookies():  # 循环遍历序列或集合
            name, value = c.get("name"), c.get("value")  # 执行语句（保持原逻辑不变）
            if name and value:  # 条件判断语句
                s.cookies.set(name, value, domain=c.get("domain") or ".kuaikanmanhua.com", path=c.get("path") or "/")  # 执行语句（保持原逻辑不变）
        return s  # 返回函数执行结果

    @staticmethod  # 执行语句（保持原逻辑不变）
    def _try_fetch_from_nuxt_state(driver) -> Optional[List[Dict[str, Any]]]:  # 定义函数
        try:  # 异常捕获块开始
            nuxt = driver.execute_script("return window.__NUXT__ || window.__nuxt__ || null;")  # 执行 JavaScript 脚本（如滚动页面或修改属性）
            if not nuxt:  # 条件判断语句
                return None  # 返回函数执行结果
            candidates = []  # 执行语句（保持原逻辑不变）
            def walk(o):  # 定义函数
                if isinstance(o, dict):  # 条件判断语句
                    for k in ("comics", "comicList", "list", "items"):  # 循环遍历序列或集合
                        if k in o and isinstance(o[k], list):  # 条件判断语句
                            candidates.append(o[k])  # 执行语句（保持原逻辑不变）
                    for v in o.values():  # 循环遍历序列或集合
                        walk(v)  # 执行语句（保持原逻辑不变）
                elif isinstance(o, list):  # 执行语句（保持原逻辑不变）
                    for v in o:  # 循环遍历序列或集合
                        walk(v)  # 执行语句（保持原逻辑不变）
            walk(nuxt)  # 执行语句（保持原逻辑不变）

            #取章节信息
            out = []  # 执行语句（保持原逻辑不变）
            if not candidates:  # 条件判断语句
                return None  # 返回函数执行结果
            arr = candidates[0]  # 执行语句（保持原逻辑不变）
            for it in arr:  # 循环遍历序列或集合
                if not isinstance(it, dict):  # 条件判断语句
                    continue  # 执行语句（保持原逻辑不变）
                cid = it.get("id") or it.get("comic_id") or it.get("cid")  # 章节 ID，用于拼接章节详情链接
                title = it.get("title") or it.get("name") or ""  # 漫画标题或章节标题
                epno = it.get("chapter_num") or it.get("episode_no") or it.get("no") or it.get("index")  # 章节的“第几话”编号，用于排序或显示
                if not cid and isinstance(it.get("link"), str):  # 章节 ID，用于拼接章节详情链接
                    m = re.search(r"/comic/(\d+)", it["link"])  # 执行语句（保持原逻辑不变）
                    if m:  # 条件判断语句
                        cid = m.group(1)  # 章节 ID，用于拼接章节详情链接
                if cid:  # 章节 ID，用于拼接章节详情链接
                    out.append({"id": str(cid), "title": str(title), "episode_no": epno})  # 章节 ID，用于拼接章节详情链接

            return out or None  # 返回函数执行结果
        except Exception:  # 捕获异常并处理错误
            return None  # 返回函数执行结果

    # -------------------------- 小工具 --------------------------
    @staticmethod  # 执行语句（保持原逻辑不变）
    def _safe_name(name: str) -> str:  # 定义函数
        return re.sub(r'[\\/:*?"<>|]+', "_", (name or "").strip())  # 返回函数执行结果


# ================================ MAIN 演示 ================================
if __name__ == "__main__":  # 条件判断语句
    # 按你的环境修改
    chrome_binary_path = r"D:\python_contoon\chrome-win64\chrome.exe"  # Chrome 浏览器可执行文件路径，用于启动浏览器
    chromedriver_path = r"D:\python_contoon\chromedriver-win64\chromedriver.exe"  # ChromeDriver 驱动路径，用于 Selenium 控制浏览器
    cookie_json_path = r"D:\python_contoon\kuikan\kuaikanmanhua.json"  # 保存登录 Cookie 的 JSON 文件路径
    topic_url = "https://www.kuaikanmanhua.com/web/topic/12432/"  # 存放网页或图片的链接 URL
    log_file = r"D:\python_contoon\kuikan\kuaikan.log"  # 日志文件路径（None 表示只输出到控制台）

    client = KuaikanClient(  # 执行语句（保持原逻辑不变）
        chrome_binary_path=chrome_binary_path,  # Chrome 浏览器可执行文件路径，用于启动浏览器
        chromedriver_path=chromedriver_path,  # ChromeDriver 驱动路径，用于 Selenium 控制浏览器
        cookie_json_path=cookie_json_path,  # 保存登录 Cookie 的 JSON 文件路径
        save_root=r"E:/kuaikan",  # 漫画图片保存的根目录路径
        max_workers=8,  # 下载图片时线程池的最大并发线程数
        jpg_quality=100,  # 保存图片的 JPEG 质量（范围 0-100）
        retries=3,  # 下载失败后的最大重试次数
        timeout=20,  # 网络请求或等待的超时时间（秒）
        headless=True,  # 是否启用无头模式（隐藏浏览器界面）
        log_file=log_file,  # 日志文件路径（None 表示只输出到控制台）
    )  # 执行语句（保持原逻辑不变）

    ok, msg, title, driver = client.login(topic_url)  # 存放网页或图片的链接 URL
    if not ok:  # 条件判断语句
        print("未检测到登录态，可能影响章节/图片访问。")  # 执行语句（保持原逻辑不变）

    # 获取章节（核心逻辑：NUXT -> API -> DOM）
    page_title, chapters = client.fetch_chapters(topic_url)  # 存放网页或图片的链接 URL
    print(f"[标题] {page_title} | [章节总数] {len(chapters)}")  # 漫画标题或章节标题


    # # —— 选择性下载示例 ——
    # # 1) 用字符串表达式选择：如 "1-5,8,12-15"
    select_spec = "685"       # 自己改
    ranges = client.parse_select_spec(select_spec)  # 执行语句（保持原逻辑不变）
    to_download = client.filter_by_ranges(chapters, ranges)  # 执行语句（保持原逻辑不变）

    #
    # # 2) 或者你也可以直接整段下载（把上面两行换成：to_download = chapters）
    #
    print(f"[筛选] 计划下载 {len(to_download)} 条 | 条件：{select_spec}")  # 执行语句（保持原逻辑不变）
    for ch in to_download:  # 循环遍历序列或集合
        client.download_chapter(page_title, ch)  # 漫画标题或章节标题
