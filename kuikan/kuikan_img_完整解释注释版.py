# -*- coding: utf-8 -*-
"""
KuaikanClient All-in-One
- 登录（本地 Cookie 注入）
- 获取章节（核心方式按用户给定版本，不随意改动）
- 选择性筛选章节
- 单话图片直链提取（解析 DOM）
- 多线程下载到：E:/kuaikan/漫画标题/001 第1话 XXX/001.JPG（JPEG质量100%）
"""

import os  # 导入依赖模块或对象（供后续使用）
import re  # 导入依赖模块或对象（供后续使用）
import io  # 导入依赖模块或对象（供后续使用）
import json  # 导入依赖模块或对象（供后续使用）
import time  # 导入依赖模块或对象（供后续使用）
import html as _html  # 导入依赖模块或对象（供后续使用）
import logging  # 导入依赖模块或对象（供后续使用）
import threading  # 导入依赖模块或对象（供后续使用）
from typing import List, Tuple, Dict, Any, Optional, Iterable  # 导入依赖模块或对象（供后续使用）
from urllib.parse import urlparse  # 导入依赖模块或对象（供后续使用）
from concurrent.futures import ThreadPoolExecutor, as_completed  # 导入依赖模块或对象（供后续使用）

import requests  # 导入依赖模块或对象（供后续使用）
from PIL import Image  # 导入依赖模块或对象（供后续使用）

from selenium import webdriver  # 导入依赖模块或对象（供后续使用）
from selenium.webdriver.chrome.service import Service  # 导入依赖模块或对象（供后续使用）
from selenium.webdriver.chrome.options import Options  # 导入依赖模块或对象（供后续使用）
from selenium.webdriver.common.by import By  # 导入依赖模块或对象（供后续使用）
from selenium.webdriver.support.ui import WebDriverWait  # 导入依赖模块或对象（供后续使用）
from selenium.webdriver.support import expected_conditions as EC  # 导入依赖模块或对象（供后续使用）


# ========================== 日志工具 ==========================
def setup_logger(log_file: Optional[str] = None, level=logging.INFO):  # 定义日志初始化函数，配置控制台/文件双通道输出
    fmt = "%(asctime)s [%(levelname)s] - %(message)s"  # 执行语句：完成该行所描述的具体操作
    datefmt = "%H:%M:%S"  # 执行语句：完成该行所描述的具体操作
    logger = logging.getLogger("kuaikan")  # 获取名为 'kuaikan' 的日志记录器实例
    logger.setLevel(level)  # 设置日志器日志级别（影响输出详略）
    logger.handlers.clear()  # 执行语句：完成该行所描述的具体操作

    sh = logging.StreamHandler()  # 创建控制台日志处理器（输出到终端）
    sh.setLevel(level)  # 执行语句：完成该行所描述的具体操作
    sh.setFormatter(logging.Formatter(fmt, datefmt=datefmt))  # 执行语句：完成该行所描述的具体操作
    logger.addHandler(sh)  # 将日志处理器挂载到日志器上

    if log_file:  # 执行语句：完成该行所描述的具体操作
        fh = logging.FileHandler(log_file, encoding="utf-8")  # 创建文件日志处理器（输出到日志文件）
        fh.setLevel(level)  # 执行语句：完成该行所描述的具体操作
        fh.setFormatter(logging.Formatter(fmt, datefmt=datefmt))  # 执行语句：完成该行所描述的具体操作
        logger.addHandler(fh)  # 将日志处理器挂载到日志器上
    return logger  # 返回已配置好的日志器对象


# ========================== 主类 ==========================
class KuaikanClient:  # 定义客户端主类：封装登录、抓取章节、解析图片与下载
    """
    快看漫画客户端（封装：登录 / 章节抓取 / 选择过滤 / 图片解析 / 多线程下载）
    - 章节抓取核心方式与用户提供版本一致（NUXT -> API -> DOM）
    """

    def __init__(  # 类构造函数：接收环境与下载行为配置
        self,  # 执行语句：完成该行所描述的具体操作
        chrome_binary_path: str,  # 执行语句：完成该行所描述的具体操作
        chromedriver_path: str,  # 执行语句：完成该行所描述的具体操作
        cookie_json_path: str,  # 执行语句：完成该行所描述的具体操作
        save_root: str = r"E:/kuaikan",  # 执行语句：完成该行所描述的具体操作
        max_workers: int = 8,  # 执行语句：完成该行所描述的具体操作
        jpg_quality: int = 100,  # 执行语句：完成该行所描述的具体操作
        retries: int = 3,  # 执行语句：完成该行所描述的具体操作
        timeout: int = 20,  # 执行语句：完成该行所描述的具体操作
        headless: bool = False,  # 执行语句：完成该行所描述的具体操作
        log_file: Optional[str] = None,  # 执行语句：完成该行所描述的具体操作
    ):  # 执行语句：完成该行所描述的具体操作
        self.chrome_binary_path = chrome_binary_path  # 保存 Chrome 可执行文件路径到实例属性
        self.chromedriver_path = chromedriver_path  # 保存 ChromeDriver 驱动路径到实例属性
        self.cookie_json_path = cookie_json_path  # 保存 Cookie JSON 路径到实例属性

        self.save_root = save_root  # 保存下载根目录到实例属性
        self.max_workers = max_workers  # 保存最大并发线程数到实例属性
        self.jpg_quality = jpg_quality  # 保存 JPG 图片质量到实例属性
        self.retries = retries  # 保存下载重试次数到实例属性
        self.timeout = timeout  # 保存超时秒数到实例属性
        self.headless = headless  # 保存无头模式开关到实例属性

        os.makedirs(self.save_root, exist_ok=True)  # 确保保存根目录存在（若不存在则创建）

        self.log = setup_logger(log_file)  # 初始化日志记录器（控制台/文件输出）并保存到实例
        self.log.info("初始化 KuaikanClient 参数：save_root=%s | workers=%d | jpg=%d | retries=%d | timeout=%ds | headless=%s",  # 执行语句：完成该行所描述的具体操作
                      self.save_root, self.max_workers, self.jpg_quality, self.retries, self.timeout, self.headless)  # 保存下载根目录到实例属性

        self.driver: Optional[webdriver.Chrome] = None  # 声明浏览器驱动属性，初始为 None
        self._lock = threading.Lock()  # 创建线程锁（并发写文件时保证原子性）

    # -------------------------- 登录 --------------------------
    def login(self, topic_url: str, base_url: str = "https://www.kuaikanmanhua.com"  # 登录功能：注入本地 Cookie，进入专题页，确认登录态
              ) -> Tuple[bool, str, str, webdriver.Chrome]:  # 执行语句：完成该行所描述的具体操作
        """
        注入本地 Cookie 并打开专题页
        :return: (ok, msg, title, driver)
        """
        self.log.info("开始登录：注入 Cookie -> %s", self.cookie_json_path)  # 执行语句：完成该行所描述的具体操作
        self.driver = self._build_driver(self.chrome_binary_path, self.chromedriver_path, self.headless)  # 根据配置启动 Chrome 浏览器（可选无头模式）

        self.driver.get(base_url)  # 先打开站点首页，便于设置 Cookie 域
        time.sleep(1.0)  # 执行语句：完成该行所描述的具体操作

        cookies = self._load_cookies_from_file(self.cookie_json_path)  # 读取本地 Cookie JSON 文件以用于注入
        added = 0  # 执行语句：完成该行所描述的具体操作
        for c in cookies:  # 遍历读取到的 cookies，逐条构建可注入格式
            addable = {"name": c.get("name"), "value": c.get("value")}  # 构造最小 cookie 字典（必须包含 name 与 value）
            if not addable["name"]:  # 跳过无效 cookie（缺少名称）
                continue  # 执行语句：完成该行所描述的具体操作
            if c.get("domain"):  # 执行语句：完成该行所描述的具体操作
                addable["domain"] = c["domain"]  # 若原始 cookie 含域名，则附带 domain 字段
            if c.get("path"):  # 执行语句：完成该行所描述的具体操作
                addable["path"] = c["path"]  # 若原始 cookie 含路径，则附带 path 字段
            if c.get("expiry"):  # 执行语句：完成该行所描述的具体操作
                try:  # 执行语句：完成该行所描述的具体操作
                    addable["expiry"] = int(c["expiry"])  # 若包含过期时间，将其转为整数时间戳
                except Exception:  # 执行语句：完成该行所描述的具体操作
                    pass  # 执行语句：完成该行所描述的具体操作
            if "secure" in c:  # 执行语句：完成该行所描述的具体操作
                addable["secure"] = bool(c["secure"])  # 保留 secure 标记（仅 HTTPS 发送）
            if "httpOnly" in c:  # 执行语句：完成该行所描述的具体操作
                addable["httpOnly"] = bool(c["httpOnly"])  # 保留 httpOnly 标记（前端脚本不可读取）
            try:  # 执行语句：完成该行所描述的具体操作
                self.driver.add_cookie(addable)  # 向当前浏览器会话注入该 cookie
                added += 1  # 执行语句：完成该行所描述的具体操作
            except Exception:  # 执行语句：完成该行所描述的具体操作
                pass  # 执行语句：完成该行所描述的具体操作
        self.log.info("已注入 Cookie 条数：%d", added)  # 执行语句：完成该行所描述的具体操作

        self.driver.get(topic_url)  # 打开漫画专题页（带登录态）
        try:  # 执行语句：完成该行所描述的具体操作
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))  # 显式等待页面主体元素出现，确保加载完成
        except Exception:  # 执行语句：完成该行所描述的具体操作
            pass  # 执行语句：完成该行所描述的具体操作
        time.sleep(1.0)  # 执行语句：完成该行所描述的具体操作

        title = self.driver.title or ""  # 获取当前页面标题（用于日志和返回值）
        ok = self._check_login_status()  # 检测是否已处于登录状态（通过 DOM/Cookie）
        msg = "注入成功，登录成功" if ok else "Cookie 注入完成，但未检测到登录态"  # 执行语句：完成该行所描述的具体操作
        self.log.info("[登录] %s | 页面标题：%s", msg, title)  # 执行语句：完成该行所描述的具体操作
        return ok, msg, title, self.driver  # 返回登录状态、提示信息、页面标题与驱动对象

    def _check_login_status(self) -> bool:  # 通过页面 DOM 与 cookies 粗略判断是否登录成功
        ok = False  # 执行语句：完成该行所描述的具体操作
        try:  # 执行语句：完成该行所描述的具体操作
            no_user = self.driver.find_elements(By.CSS_SELECTOR, ".User .noUser")  # 查找未登录占位元素，若无则倾向为已登录
            if not no_user:  # 执行语句：完成该行所描述的具体操作
                ok = True  # 执行语句：完成该行所描述的具体操作
            txt = self.driver.page_source  # 读取页面 HTML 文本用于包含关键词判断
            if ("登录" in txt or "注册" in txt) and no_user:  # 执行语句：完成该行所描述的具体操作
                ok = False  # 执行语句：完成该行所描述的具体操作
            site_cookies = self.driver.get_cookies()  # 读取站点 cookies，用关键字段判断是否登录
            names = " ".join([c["name"].lower() for c in site_cookies if "name" in c])  # 执行语句：完成该行所描述的具体操作
            if any(k in names for k in ["token", "uid", "session", "auth"]):  # 若存在 token/uid/session/auth 等关键 cookie 视为已登录
                ok = True  # 执行语句：完成该行所描述的具体操作
        except Exception:  # 执行语句：完成该行所描述的具体操作
            pass  # 执行语句：完成该行所描述的具体操作
        return ok  # 执行语句：完成该行所描述的具体操作

    # -------------------------- 章节抓取（核心方式保持不变） --------------------------
    def fetch_chapters(self, topic_url: str, limit: int = 60  # 抓取章节列表：优先从 NUXT 状态提取，组装 order/url 等字段
                       ) -> Tuple[str, List[Dict[str, Any]]]:  # 执行语句：完成该行所描述的具体操作
        """
        章节字段：order、episode_no、title、url、id
        逻辑：NUXT -> API -> DOM（与你提供的版本一致，尽量不改动）
        """
        # ==== 新增：用页面信息区替换/净化标题 ====

        #取标题
        page_title   = self.driver.find_element(By.CSS_SELECTOR, ".right .title").text.strip()  # 从信息区读取漫画标题（更干净，剔除 SEO 后缀）
        #取作者
        page_author = self.driver.find_element(By.CSS_SELECTOR, ".right .nickname").text.strip()  # 从信息区读取作者昵称信息（可用于日志展示）
        #取简介
        page_ntro = self.driver.find_element(By.CSS_SELECTOR, ".comicIntro .detailsBox p").text.strip()  # 从信息区读取漫画简介（可用于日志展示或保存）

        if not self.driver:  # 执行语句：完成该行所描述的具体操作
            raise RuntimeError("请先调用 login() 完成登录。")  # 执行语句：完成该行所描述的具体操作

        self.log.info("[章节] 尝试从 NUXT 状态读取")  # 执行语句：完成该行所描述的具体操作
        items = self._try_fetch_from_nuxt_state(self.driver)  # 尝试从 window.__NUXT__ 树中提取章节数组
        for i, ch in enumerate(items, 1):  # 为每个章节标注顺序序号（order 从 1 开始）
            ch["order"] = i  # 执行语句：完成该行所描述的具体操作
            ch["url"] = self._build_comic_url(str(ch.get("id")))  # 根据章节 ID 拼接章节详情页 URL
        self.log.info("[章节] 获取完成：共 %d 条", len(items))  # 执行语句：完成该行所描述的具体操作
        return page_title, items  # 返回页面标题与完整章节列表

    def format_chapters(self, chapters: List[Dict[str, Any]], with_url: bool = True) -> List[str]:  # 执行语句：完成该行所描述的具体操作
        lines = []  # 执行语句：完成该行所描述的具体操作
        for ch in chapters:  # 执行语句：完成该行所描述的具体操作
            idx = f"{ch.get('order', 0):03d}"  # 执行语句：完成该行所描述的具体操作
            title = ch.get("title", "")  # 执行语句：完成该行所描述的具体操作
            url = ch.get("url", "")  # 执行语句：完成该行所描述的具体操作
            if with_url:  # 执行语句：完成该行所描述的具体操作
                lines.append(f"{idx} {title} {url}".strip())  # 执行语句：完成该行所描述的具体操作
            else:  # 执行语句：完成该行所描述的具体操作
                lines.append(f"{idx} {title}".strip())  # 执行语句：完成该行所描述的具体操作
        return lines  # 执行语句：完成该行所描述的具体操作

    # -------------------------- 选择性下载（筛选） --------------------------
    @staticmethod  # 执行语句：完成该行所描述的具体操作
    def parse_select_spec(spec: str) -> List[Tuple[int, int]]:  # 解析选择表达式（如 1-3,6,8-10）为区间列表
        """
        解析选择串：如 "1-3,6,8-10" -> [(1,3),(6,6),(8,10)]
        """
        out = []  # 执行语句：完成该行所描述的具体操作
        if not spec:  # 执行语句：完成该行所描述的具体操作
            return out  # 执行语句：完成该行所描述的具体操作
        for part in spec.split(","):  # 按逗号切分多个片段
            part = part.strip()  # 执行语句：完成该行所描述的具体操作
            if not part:  # 执行语句：完成该行所描述的具体操作
                continue  # 执行语句：完成该行所描述的具体操作
            if "-" in part:  # 执行语句：完成该行所描述的具体操作
                a, b = part.split("-", 1)  # 执行语句：完成该行所描述的具体操作
                try:  # 执行语句：完成该行所描述的具体操作
                    a, b = int(a), int(b)  # 执行语句：完成该行所描述的具体操作
                    if a > b:  # 执行语句：完成该行所描述的具体操作
                        a, b = b, a  # 执行语句：完成该行所描述的具体操作
                    out.append((a, b))  # 执行语句：完成该行所描述的具体操作
                except Exception:  # 执行语句：完成该行所描述的具体操作
                    continue  # 执行语句：完成该行所描述的具体操作
            else:  # 执行语句：完成该行所描述的具体操作
                try:  # 执行语句：完成该行所描述的具体操作
                    n = int(part)  # 执行语句：完成该行所描述的具体操作
                    out.append((n, n))  # 单个数字转为 (n, n) 的闭区间
                except Exception:  # 执行语句：完成该行所描述的具体操作
                    continue  # 执行语句：完成该行所描述的具体操作
        return out  # 执行语句：完成该行所描述的具体操作

    @staticmethod  # 执行语句：完成该行所描述的具体操作
    def filter_by_ranges(chapters: List[Dict[str, Any]], ranges: List[Tuple[int, int]]) -> List[Dict[str, Any]]:  # 按给定区间过滤章节（基于 order 字段）
        if not ranges:  # 执行语句：完成该行所描述的具体操作
            return chapters  # 执行语句：完成该行所描述的具体操作
        def hit(n: int):  # 执行语句：完成该行所描述的具体操作
            return any(a <= n <= b for a, b in ranges)  # 判断序号是否命中任一选择区间
        return [c for c in chapters if hit(c.get("order", 0))]  # 返回满足选择条件的章节子集

    # -------------------------- 单话图片提取（DOM 解析） --------------------------
    def fetch_comic_images_by_parsing(self, chapter_url: str, max_scroll: int = 10, wait_sec: float = 0.6) -> List[str]:  # 打开章节页，通过滚动触发懒加载，收集图片链接
        """
        用 Selenium 打开章节页，滚动触发懒加载，抓取 .imgList .img-box img.img 的 data-src/src
        """
        if not self.driver:  # 执行语句：完成该行所描述的具体操作
            raise RuntimeError("请先调用 login() 完成登录。")  # 执行语句：完成该行所描述的具体操作
        self.log.info("[图片] 打开章节页：%s", chapter_url)  # 执行语句：完成该行所描述的具体操作
        d = self.driver  # 执行语句：完成该行所描述的具体操作
        d.get(chapter_url)  # 执行语句：完成该行所描述的具体操作
        WebDriverWait(d, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".imgList")))  # 显式等待页面主体元素出现，确保加载完成

        last_height = 0  # 执行语句：完成该行所描述的具体操作
        for i in range(max_scroll):  # 执行语句：完成该行所描述的具体操作
            d.execute_script("window.scrollTo(0, document.body.scrollHeight);")  # 模拟滚动到底部以触发图片懒加载
            time.sleep(wait_sec)  # 执行语句：完成该行所描述的具体操作
            new_height = d.execute_script("return document.body.scrollHeight")  # 获取页面总高度以判断是否还有新内容加载
            self.log.debug("[图片] 滚动第 %d 次 | 高度=%s", i + 1, new_height)  # 执行语句：完成该行所描述的具体操作
            if new_height == last_height:  # 执行语句：完成该行所描述的具体操作
                break  # 执行语句：完成该行所描述的具体操作
            last_height = new_height  # 执行语句：完成该行所描述的具体操作

        html_text = d.page_source  # 获取章节页完整 HTML 文本
        urls = self.parse_img_urls_from_html(html_text)  # 调用 HTML 解析函数提取图片直链
        self.log.info("[图片] 共抽取 %d 张", len(urls))  # 执行语句：完成该行所描述的具体操作
        return urls  # 执行语句：完成该行所描述的具体操作

    @staticmethod  # 执行语句：完成该行所描述的具体操作
    def parse_img_urls_from_html(html_text: str) -> List[str]:  # 解析 HTML，只提取每个 .img-box 中第一张图片链接
        """
        解析章节 HTML：只取 .imgList .img-box 里的第一张 img.img 的 data-src/src
        """
        from bs4 import BeautifulSoup  # 导入依赖模块或对象（供后续使用）
        soup = BeautifulSoup(html_text, "html.parser")  # 用 BS4 解析 HTML（便于 CSS 选择器检索）
        out, seen = [], set()  # 执行语句：完成该行所描述的具体操作
        for box in soup.select(".imgList .img-box"):  # 遍历每个图片容器 .img-box
            img = box.select_one("img.img")  # 定位第一张图片元素（类名为 img）
            if not img:  # 执行语句：完成该行所描述的具体操作
                continue  # 执行语句：完成该行所描述的具体操作
            u = img.get("data-src") or img.get("src") or ""  # 优先读 data-src，其次读 src，得到图片 URL
            u = _html.unescape((u or "").strip())  # 反转义 HTML 实体，得到净化后的 URL
            if not u:  # 执行语句：完成该行所描述的具体操作
                continue  # 执行语句：完成该行所描述的具体操作
            if u.startswith("//"):  # 协议相对地址补全为 https 方案
                u = "https:" + u  # 执行语句：完成该行所描述的具体操作
            if u not in seen:  # 用集合去重，确保每张图片只计一次
                seen.add(u)  # 执行语句：完成该行所描述的具体操作
                out.append(u)  # 执行语句：完成该行所描述的具体操作
        return out  # 执行语句：完成该行所描述的具体操作

    # -------------------------- 多线程下载 --------------------------
    def download_chapter(  # 下载单话图片到本地，按章节建文件夹并顺序命名
        self,  # 执行语句：完成该行所描述的具体操作
        topic_title: str,  # 执行语句：完成该行所描述的具体操作
        chapter: Dict[str, Any],  # 执行语句：完成该行所描述的具体操作
        referer: Optional[str] = None,  # 执行语句：完成该行所描述的具体操作
    ) -> None:  # 执行语句：完成该行所描述的具体操作
        """
        下载单话到：E:/kuaikan/{topic_title}/{001 第1话 XXX}/001.JPG ...
        """
        order = chapter.get("order", 0)  # 执行语句：完成该行所描述的具体操作
        chap_title = (chapter.get("title") or "").strip().replace("\n", " ")  # 执行语句：完成该行所描述的具体操作
        folder_name = f"{order:03d}  {chap_title}".strip()  # 构造章节文件夹名：三位序号 + 章节标题
        save_dir = os.path.join(self.save_root, self._safe_name(topic_title), self._safe_name(folder_name))  # 拼接保存路径并对标题做文件名安全化处理
        os.makedirs(save_dir, exist_ok=True)  # 执行语句：完成该行所描述的具体操作

        chapter_url = chapter.get("url")  # 执行语句：完成该行所描述的具体操作
        self.log.info("[下载] 开始：%s -> %s", chapter_url, save_dir)  # 执行语句：完成该行所描述的具体操作

        # 取图片直链
        img_urls = self.fetch_comic_images_by_parsing(chapter_url)  # 获取该章节的所有图片直链
        if not img_urls:  # 执行语句：完成该行所描述的具体操作
            self.log.warning("[下载] 未获取到图片：%s", chapter_url)  # 执行语句：完成该行所描述的具体操作
            return  # 执行语句：完成该行所描述的具体操作

        # 多线程保存
        headers = {  # 执行语句：完成该行所描述的具体操作
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "  # 执行语句：完成该行所描述的具体操作
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),  # 执行语句：完成该行所描述的具体操作
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",  # 执行语句：完成该行所描述的具体操作
            "Referer": referer or chapter_url,  # 执行语句：完成该行所描述的具体操作
        }  # 执行语句：完成该行所描述的具体操作

        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:  # 创建线程池，并发提交图片下载任务
            futures = []  # 执行语句：完成该行所描述的具体操作
            for idx, u in enumerate(img_urls, 1):  # 执行语句：完成该行所描述的具体操作
                out_path = os.path.join(save_dir, f"{idx:03d}.JPG")  # 执行语句：完成该行所描述的具体操作
                futures.append(ex.submit(self._download_one_image, u, out_path, headers))  # 执行语句：完成该行所描述的具体操作
            for fut in as_completed(futures):  # 遍历已完成的任务，捕获并记录异常
                try:  # 执行语句：完成该行所描述的具体操作
                    fut.result()  # 执行语句：完成该行所描述的具体操作
                except Exception as e:  # 执行语句：完成该行所描述的具体操作
                    self.log.error("[下载] 子任务异常：%s", e)  # 执行语句：完成该行所描述的具体操作

        self.log.info("[下载] 完成：%s | 共 %d 张", folder_name, len(img_urls))  # 日志记录本章节下载完成与图片数量

    def _download_one_image(self, url: str, out_path: str, headers: Dict[str, str]) -> None:  # 下载一张图片，必要时转码为 JPG，支持重试
        """
        下载单张图片，必要时转存为 JPG（quality=100），含重试。
        """
        if os.path.exists(out_path):  # 若目标文件已存在则跳过（避免重复下载）
            self.log.debug("[跳过] 已存在：%s", out_path)  # 执行语句：完成该行所描述的具体操作
            return  # 执行语句：完成该行所描述的具体操作

        sess = self._requests_session_from_selenium(self.driver)  # 基于当前浏览器 cookies 构建 requests 会话
        for attempt in range(1, self.retries + 1):  # 执行语句：完成该行所描述的具体操作
            try:  # 执行语句：完成该行所描述的具体操作
                r = sess.get(url, headers=headers, timeout=self.timeout, stream=True)  # 以流式方式下载图片数据
                r.raise_for_status()  # 状态码校验（非 2xx 抛出异常进入重试）
                content = r.content  # 执行语句：完成该行所描述的具体操作

                # 识别格式并转 JPG
                fmt = self._guess_ext_from_url_or_headers(url, r.headers)  # 根据 URL 或响应头推断图片格式扩展名
                if fmt in (".jpg", ".jpeg"):  # 执行语句：完成该行所描述的具体操作
                    with open(out_path, "wb") as f:  # 执行语句：完成该行所描述的具体操作
                        f.write(content)  # 执行语句：完成该行所描述的具体操作
                else:  # 执行语句：完成该行所描述的具体操作
                    im = Image.open(io.BytesIO(content)).convert("RGB")  # 将非 JPG 图片解码为 RGB 后再保存为 JPG
                    im.save(out_path, format="JPEG", quality=self.jpg_quality, optimize=True)  # 以指定质量保存为 JPEG 文件

                self.log.debug("[保存] %s <- %s", out_path, url)  # 执行语句：完成该行所描述的具体操作
                return  # 执行语句：完成该行所描述的具体操作
            except Exception as e:  # 执行语句：完成该行所描述的具体操作
                self.log.warning("[重试 %d/%d] 下载失败：%s | %s", attempt, self.retries, url, e)  # 执行语句：完成该行所描述的具体操作
                time.sleep(0.6)  # 执行语句：完成该行所描述的具体操作
        self.log.error("[失败] 放弃：%s", url)  # 执行语句：完成该行所描述的具体操作

    @staticmethod  # 执行语句：完成该行所描述的具体操作
    def _guess_ext_from_url_or_headers(url: str, headers: Dict[str, str]) -> str:  # 根据 URL 扩展名或 Content-Type 推断文件后缀
        path = urlparse(url).path.lower()  # 解析 URL 路径并转为小写以便匹配后缀
        for ext in (".jpg", ".jpeg", ".png", ".webp"):  # 执行语句：完成该行所描述的具体操作
            if path.endswith(ext):  # 执行语句：完成该行所描述的具体操作
                return ext  # 执行语句：完成该行所描述的具体操作
        ct = headers.get("Content-Type", "").lower()  # 执行语句：完成该行所描述的具体操作
        if "jpeg" in ct:  # 执行语句：完成该行所描述的具体操作
            return ".jpg"  # 执行语句：完成该行所描述的具体操作
        if "png" in ct:  # 执行语句：完成该行所描述的具体操作
            return ".png"  # 执行语句：完成该行所描述的具体操作
        if "webp" in ct:  # 执行语句：完成该行所描述的具体操作
            return ".webp"  # 执行语句：完成该行所描述的具体操作
        return ".jpg"  # 执行语句：完成该行所描述的具体操作

    # -------------------------- Selenium/requests/工具函数（来自章节代码的实现，尽量不改动，仅加日志） --------------------------
    @staticmethod  # 执行语句：完成该行所描述的具体操作
    def _build_comic_url(comic_id: str) -> str:  # 拼接章节详情页的固定 URL 格式
        return f"https://www.kuaikanmanhua.com/web/comic/{comic_id}"  # 执行语句：完成该行所描述的具体操作

    @staticmethod  # 执行语句：完成该行所描述的具体操作
    def _load_cookies_from_file(cookie_json_path: str) -> List[Dict[str, Any]]:  # 从 JSON 文件读取 cookies 列表（支持两种结构）
        with open(cookie_json_path, "r", encoding="utf-8") as f:  # 执行语句：完成该行所描述的具体操作
            data = json.load(f)  # 执行语句：完成该行所描述的具体操作
        if isinstance(data, dict) and "cookies" in data:  # 兼容浏览器导出的 dict 结构：取 data['cookies']
            cookies = data["cookies"]  # 执行语句：完成该行所描述的具体操作
        elif isinstance(data, list):  # 执行语句：完成该行所描述的具体操作
            cookies = data  # 执行语句：完成该行所描述的具体操作
        else:  # 执行语句：完成该行所描述的具体操作
            raise ValueError("不识别的 cookies JSON 格式，请确认文件内容。")  # 执行语句：完成该行所描述的具体操作
        if not isinstance(cookies, list):  # 执行语句：完成该行所描述的具体操作
            raise ValueError("cookies 应为列表。")  # 若数据结构不合法则抛出异常提示
        return cookies  # 执行语句：完成该行所描述的具体操作

    def _build_driver(self, chrome_binary_path: str, chromedriver_path: str, headless: bool = False) -> webdriver.Chrome:  # 构建 Selenium Chrome 驱动并进行反自动化设置
        options = Options()  # 执行语句：完成该行所描述的具体操作
        options.binary_location = chrome_binary_path  # 指定 Chrome 可执行文件路径（避免系统默认冲突）
        if headless:  # 执行语句：完成该行所描述的具体操作
            options.add_argument("--headless=new")  # 启用新版无头模式（Chrome 109+，更接近真实渲染）
        options.add_argument("--disable-gpu")  # 禁用 GPU 加速（无头或服务器环境更稳定）
        options.add_argument("--no-sandbox")  # 关闭沙箱（部分 Linux 环境需要）
        options.add_argument("--disable-dev-shm-usage")  # 避免 /dev/shm 容量不足导致的崩溃
        options.add_argument("--window-size=1400,900")  # 设置虚拟窗口尺寸（影响懒加载与布局）
        options.add_experimental_option("excludeSwitches", ["enable-automation"])  # 去除 'Chrome 正在受到自动测试软件控制' 提示
        options.add_experimental_option('useAutomationExtension', False)  # 禁用自动化扩展，降低被检测风险
        options.page_load_strategy = "eager"  # 设置页面加载策略为 eager（不等所有资源完成）
        service = Service(executable_path=chromedriver_path)  # 配置 ChromeDriver 服务（指定驱动可执行文件）
        driver = webdriver.Chrome(service=service, options=options)  # 创建 Chrome WebDriver 实例
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {  # 在新文档加载前注入 JS，隐藏 navigator.webdriver
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"  # 执行语句：完成该行所描述的具体操作
        })  # 执行语句：完成该行所描述的具体操作
        return driver  # 执行语句：完成该行所描述的具体操作

    @staticmethod  # 执行语句：完成该行所描述的具体操作
    def _requests_session_from_selenium(driver: webdriver.Chrome) -> requests.Session:  # 把 Selenium 的 cookies 转为 requests 可用的会话
        s = requests.Session()  # 执行语句：完成该行所描述的具体操作
        s.headers.update({  # 执行语句：完成该行所描述的具体操作
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0.0.0 Safari/537.36",  # 执行语句：完成该行所描述的具体操作
            "Accept": "application/json, text/plain, */*",  # 执行语句：完成该行所描述的具体操作
            "Referer": "https://www.kuaikanmanhua.com/"  # 执行语句：完成该行所描述的具体操作
        })  # 执行语句：完成该行所描述的具体操作
        for c in driver.get_cookies():  # 遍历浏览器中的 cookies 并迁移到会话中
            name, value = c.get("name"), c.get("value")  # 执行语句：完成该行所描述的具体操作
            if name and value:  # 执行语句：完成该行所描述的具体操作
                s.cookies.set(name, value, domain=c.get("domain") or ".kuaikanmanhua.com", path=c.get("path") or "/")  # 把每个 cookie 写入 requests 会话以复用登录态
        return s  # 执行语句：完成该行所描述的具体操作

    @staticmethod  # 执行语句：完成该行所描述的具体操作
    def _try_fetch_from_nuxt_state(driver) -> Optional[List[Dict[str, Any]]]:  # 从页面 window.__NUXT__ 树提取章节数组（优先方案）
        try:  # 执行语句：完成该行所描述的具体操作
            nuxt = driver.execute_script("return window.__NUXT__ || window.__nuxt__ || null;")  # 通过 JS 读取全局 NUXT 状态对象
            if not nuxt:  # 执行语句：完成该行所描述的具体操作
                return None  # 执行语句：完成该行所描述的具体操作
            candidates = []  # 执行语句：完成该行所描述的具体操作
            def walk(o):  # 执行语句：完成该行所描述的具体操作
                if isinstance(o, dict):  # 执行语句：完成该行所描述的具体操作
                    for k in ("comics", "comicList", "list", "items"):  # 在常见字段名下收集数组引用（候选章节列表）
                        if k in o and isinstance(o[k], list):  # 执行语句：完成该行所描述的具体操作
                            candidates.append(o[k])  # 执行语句：完成该行所描述的具体操作
                    for v in o.values():  # 执行语句：完成该行所描述的具体操作
                        walk(v)  # 执行语句：完成该行所描述的具体操作
                elif isinstance(o, list):  # 执行语句：完成该行所描述的具体操作
                    for v in o:  # 执行语句：完成该行所描述的具体操作
                        walk(v)  # 执行语句：完成该行所描述的具体操作
            walk(nuxt)  # 对 NUXT 根对象执行递归收集

            #取章节信息
            out = []  # 执行语句：完成该行所描述的具体操作
            if not candidates:  # 执行语句：完成该行所描述的具体操作
                return None  # 执行语句：完成该行所描述的具体操作
            arr = candidates[0]  # 仅取第一个候选数组，避免跨列表重复
            for it in arr:  # 执行语句：完成该行所描述的具体操作
                if not isinstance(it, dict):  # 执行语句：完成该行所描述的具体操作
                    continue  # 执行语句：完成该行所描述的具体操作
                cid = it.get("id") or it.get("comic_id") or it.get("cid")  # 从字典项中提取章节 ID（多字段兜底）
                title = it.get("title") or it.get("name") or ""  # 从字典项中提取章节标题（多字段兜底）
                epno = it.get("chapter_num") or it.get("episode_no") or it.get("no") or it.get("index")  # 提取章节话数编号（多字段兜底）
                if not cid and isinstance(it.get("link"), str):  # 执行语句：完成该行所描述的具体操作
                    m = re.search(r"/comic/(\d+)", it["link"])  # 若无 ID 则从链接中用正则提取 /comic/数字
                    if m:  # 执行语句：完成该行所描述的具体操作
                        cid = m.group(1)  # 执行语句：完成该行所描述的具体操作
                if cid:  # 执行语句：完成该行所描述的具体操作
                    out.append({"id": str(cid), "title": str(title), "episode_no": epno})  # 将提取到的章节信息规范化后加入结果列表

            return out or None  # 执行语句：完成该行所描述的具体操作
        except Exception:  # 执行语句：完成该行所描述的具体操作
            return None  # 执行语句：完成该行所描述的具体操作

    # -------------------------- 小工具 --------------------------
    @staticmethod  # 执行语句：完成该行所描述的具体操作
    def _safe_name(name: str) -> str:  # 替换非法文件名字符为下划线，保证可保存
        return re.sub(r'[\\/:*?"<>|]+', "_", (name or "").strip())  # 执行语句：完成该行所描述的具体操作


# ================================ MAIN 演示 ================================
if __name__ == "__main__":  # 脚本直接运行时的演示入口（非被导入时）
    # 按你的环境修改
    chrome_binary_path = r"D:\python_contoon\chrome-win64\chrome.exe"  # 本地 Chrome 可执行文件路径（按你的环境修改）
    chromedriver_path = r"D:\python_contoon\chromedriver-win64\chromedriver.exe"  # 本地 ChromeDriver 路径（按你的环境修改）
    cookie_json_path = r"D:\python_contoon\kuikan\kuaikanmanhua.json"  # 本地 Cookie JSON 路径（按你的环境修改）
    topic_url = "https://www.kuaikanmanhua.com/web/topic/12432/"  # 目标漫画专题页地址（要抓取的入口页）
    log_file = r"D:\python_contoon\kuikan\kuaikan.log"  # 日志输出文件路径（便于排错与记录）

    client = KuaikanClient(  # 构造客户端实例并传入各项配置
        chrome_binary_path=chrome_binary_path,  # 执行语句：完成该行所描述的具体操作
        chromedriver_path=chromedriver_path,  # 执行语句：完成该行所描述的具体操作
        cookie_json_path=cookie_json_path,  # 执行语句：完成该行所描述的具体操作
        save_root=r"E:/kuaikan",  # 执行语句：完成该行所描述的具体操作
        max_workers=8,  # 执行语句：完成该行所描述的具体操作
        jpg_quality=100,  # 执行语句：完成该行所描述的具体操作
        retries=3,  # 执行语句：完成该行所描述的具体操作
        timeout=20,  # 执行语句：完成该行所描述的具体操作
        headless=True,  # 执行语句：完成该行所描述的具体操作
        log_file=log_file,  # 执行语句：完成该行所描述的具体操作
    )  # 执行语句：完成该行所描述的具体操作

    ok, msg, title, driver = client.login(topic_url)  # 执行登录流程并返回状态/提示/标题/驱动
    if not ok:  # 若未检测到登录态则提示可能影响抓取
        print("未检测到登录态，可能影响章节/图片访问。")  # 执行语句：完成该行所描述的具体操作

    # 获取章节（核心逻辑：NUXT -> API -> DOM）
    page_title, chapters = client.fetch_chapters(topic_url)  # 抓取章节列表（返回标题与章节数组）
    print(f"[标题] {page_title} | [章节总数] {len(chapters)}")  # 打印抓取结果统计：标题与章节总条数


    # # —— 选择性下载示例 ——
    # # 1) 用字符串表达式选择：如 "1-5,8,12-15"
    select_spec = "685"       # 自己改
    ranges = client.parse_select_spec(select_spec)  # 将选择表达式解析为可用于过滤的区间
    to_download = client.filter_by_ranges(chapters, ranges)  # 按区间过滤出目标章节列表

    #
    # # 2) 或者你也可以直接整段下载（把上面两行换成：to_download = chapters）
    #
    print(f"[筛选] 计划下载 {len(to_download)} 条 | 条件：{select_spec}")  # 执行语句：完成该行所描述的具体操作
    for ch in to_download:  # 遍历筛选出的章节并逐一下载
        client.download_chapter(page_title, ch)  # 下载指定章节的所有图片到本地目录
