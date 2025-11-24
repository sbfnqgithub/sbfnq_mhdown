# -*- coding: utf-8 -*-
"""
KuaikanClient All-in-One
- 登录（本地 Cookie 注入）
- 获取章节（核心方式按用户给定版本，不随意改动）
- 选择性筛选章节
- 单话图片直链提取（解析 DOM）
- 多线程下载到：E:/kuaikan/漫画标题/001 第1话 XXX/001.JPG（JPEG质量100%）
"""

import os
import re
import io
import json
import time
import html as _html
import logging
import threading
from typing import List, Tuple, Dict, Any, Optional, Iterable
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from PIL import Image

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ========================== 日志工具 ==========================
def setup_logger(log_file: Optional[str] = None, level=logging.INFO):
    fmt = "%(asctime)s [%(levelname)s] - %(message)s"
    datefmt = "%H:%M:%S"
    logger = logging.getLogger("kuaikan")
    logger.setLevel(level)
    logger.handlers.clear()

    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    logger.addHandler(sh)

    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        logger.addHandler(fh)
    return logger


# ========================== 主类 ==========================
class KuaikanClient:
    """
    快看漫画客户端（封装：登录 / 章节抓取 / 选择过滤 / 图片解析 / 多线程下载）
    - 章节抓取核心方式与用户提供版本一致（NUXT -> API -> DOM）
    """

    def __init__(
        self,
        chrome_binary_path: str,
        chromedriver_path: str,
        cookie_json_path: str,
        save_root: str = r"E:/kuaikan",
        max_workers: int = 8,
        jpg_quality: int = 100,
        retries: int = 3,
        timeout: int = 20,
        headless: bool = False,
        log_file: Optional[str] = None,
    ):
        self.chrome_binary_path = chrome_binary_path
        self.chromedriver_path = chromedriver_path
        self.cookie_json_path = cookie_json_path

        self.save_root = save_root
        self.max_workers = max_workers
        self.jpg_quality = jpg_quality
        self.retries = retries
        self.timeout = timeout
        self.headless = headless

        os.makedirs(self.save_root, exist_ok=True)

        self.log = setup_logger(log_file)
        self.log.info("初始化 KuaikanClient 参数：save_root=%s | workers=%d | jpg=%d | retries=%d | timeout=%ds | headless=%s",
                      self.save_root, self.max_workers, self.jpg_quality, self.retries, self.timeout, self.headless)

        self.driver: Optional[webdriver.Chrome] = None
        self._lock = threading.Lock()

    # -------------------------- 登录 --------------------------
    def login(self, topic_url: str, base_url: str = "https://www.kuaikanmanhua.com"
              ) -> Tuple[bool, str, str, webdriver.Chrome]:
        """
        注入本地 Cookie 并打开专题页
        :return: (ok, msg, title, driver)
        """
        self.log.info("开始登录：注入 Cookie -> %s", self.cookie_json_path)
        self.driver = self._build_driver(self.chrome_binary_path, self.chromedriver_path, self.headless)

        self.driver.get(base_url)
        time.sleep(1.0)

        cookies = self._load_cookies_from_file(self.cookie_json_path)
        added = 0
        for c in cookies:
            addable = {"name": c.get("name"), "value": c.get("value")}
            if not addable["name"]:
                continue
            if c.get("domain"):
                addable["domain"] = c["domain"]
            if c.get("path"):
                addable["path"] = c["path"]
            if c.get("expiry"):
                try:
                    addable["expiry"] = int(c["expiry"])
                except Exception:
                    pass
            if "secure" in c:
                addable["secure"] = bool(c["secure"])
            if "httpOnly" in c:
                addable["httpOnly"] = bool(c["httpOnly"])
            try:
                self.driver.add_cookie(addable)
                added += 1
            except Exception:
                pass
        self.log.info("已注入 Cookie 条数：%d", added)

        self.driver.get(topic_url)
        try:
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        except Exception:
            pass
        time.sleep(1.0)

        title = self.driver.title or ""
        ok = self._check_login_status()
        msg = "注入成功，登录成功" if ok else "Cookie 注入完成，但未检测到登录态"
        self.log.info("[登录] %s | 页面标题：%s", msg, title)
        return ok, msg, title, self.driver

    def _check_login_status(self) -> bool:
        ok = False
        try:
            no_user = self.driver.find_elements(By.CSS_SELECTOR, ".User .noUser")
            if not no_user:
                ok = True
            txt = self.driver.page_source
            if ("登录" in txt or "注册" in txt) and no_user:
                ok = False
            site_cookies = self.driver.get_cookies()
            names = " ".join([c["name"].lower() for c in site_cookies if "name" in c])
            if any(k in names for k in ["token", "uid", "session", "auth"]):
                ok = True
        except Exception:
            pass
        return ok

    # -------------------------- 章节抓取（核心方式保持不变） --------------------------
    def fetch_chapters(self, topic_url: str, limit: int = 60
                       ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        章节字段：order、episode_no、title、url、id
        逻辑：NUXT -> API -> DOM（与你提供的版本一致，尽量不改动）
        """
        # ==== 新增：用页面信息区替换/净化标题 ====

        #取标题
        page_title   = self.driver.find_element(By.CSS_SELECTOR, ".right .title").text.strip()
        #取作者
        page_author = self.driver.find_element(By.CSS_SELECTOR, ".right .nickname").text.strip()
        #取简介
        page_ntro = self.driver.find_element(By.CSS_SELECTOR, ".comicIntro .detailsBox p").text.strip()

        if not self.driver:
            raise RuntimeError("请先调用 login() 完成登录。")

        self.log.info("[章节] 尝试从 NUXT 状态读取")
        items = self._try_fetch_from_nuxt_state(self.driver)
        for i, ch in enumerate(items, 1):
            ch["order"] = i
            ch["url"] = self._build_comic_url(str(ch.get("id")))
        self.log.info("[章节] 获取完成：共 %d 条", len(items))
        return page_title, items

    def format_chapters(self, chapters: List[Dict[str, Any]], with_url: bool = True) -> List[str]:
        lines = []
        for ch in chapters:
            idx = f"{ch.get('order', 0):03d}"
            title = ch.get("title", "")
            url = ch.get("url", "")
            if with_url:
                lines.append(f"{idx} {title} {url}".strip())
            else:
                lines.append(f"{idx} {title}".strip())
        return lines

    # -------------------------- 选择性下载（筛选） --------------------------
    @staticmethod
    def parse_select_spec(spec: str) -> List[Tuple[int, int]]:
        """
        解析选择串：如 "1-3,6,8-10" -> [(1,3),(6,6),(8,10)]
        """
        out = []
        if not spec:
            return out
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                try:
                    a, b = int(a), int(b)
                    if a > b:
                        a, b = b, a
                    out.append((a, b))
                except Exception:
                    continue
            else:
                try:
                    n = int(part)
                    out.append((n, n))
                except Exception:
                    continue
        return out

    @staticmethod
    def filter_by_ranges(chapters: List[Dict[str, Any]], ranges: List[Tuple[int, int]]) -> List[Dict[str, Any]]:
        if not ranges:
            return chapters
        def hit(n: int):
            return any(a <= n <= b for a, b in ranges)
        return [c for c in chapters if hit(c.get("order", 0))]

    # -------------------------- 单话图片提取（DOM 解析） --------------------------
    def fetch_comic_images_by_parsing(self, chapter_url: str, max_scroll: int = 10, wait_sec: float = 0.6) -> List[str]:
        """
        用 Selenium 打开章节页，滚动触发懒加载，抓取 .imgList .img-box img.img 的 data-src/src
        """
        if not self.driver:
            raise RuntimeError("请先调用 login() 完成登录。")
        self.log.info("[图片] 打开章节页：%s", chapter_url)
        d = self.driver
        d.get(chapter_url)
        WebDriverWait(d, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".imgList")))

        last_height = 0
        for i in range(max_scroll):
            d.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(wait_sec)
            new_height = d.execute_script("return document.body.scrollHeight")
            self.log.debug("[图片] 滚动第 %d 次 | 高度=%s", i + 1, new_height)
            if new_height == last_height:
                break
            last_height = new_height

        html_text = d.page_source
        urls = self.parse_img_urls_from_html(html_text)
        self.log.info("[图片] 共抽取 %d 张", len(urls))
        return urls

    @staticmethod
    def parse_img_urls_from_html(html_text: str) -> List[str]:
        """
        解析章节 HTML：只取 .imgList .img-box 里的第一张 img.img 的 data-src/src
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_text, "html.parser")
        out, seen = [], set()
        for box in soup.select(".imgList .img-box"):
            img = box.select_one("img.img")
            if not img:
                continue
            u = img.get("data-src") or img.get("src") or ""
            u = _html.unescape((u or "").strip())
            if not u:
                continue
            if u.startswith("//"):
                u = "https:" + u
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out

    # -------------------------- 多线程下载 --------------------------
    def download_chapter(
        self,
        topic_title: str,
        chapter: Dict[str, Any],
        referer: Optional[str] = None,
    ) -> None:
        """
        下载单话到：E:/kuaikan/{topic_title}/{001 第1话 XXX}/001.JPG ...
        """
        order = chapter.get("order", 0)
        chap_title = (chapter.get("title") or "").strip().replace("\n", " ")
        folder_name = f"{order:03d}  {chap_title}".strip()
        save_dir = os.path.join(self.save_root, self._safe_name(topic_title), self._safe_name(folder_name))
        os.makedirs(save_dir, exist_ok=True)

        chapter_url = chapter.get("url")
        self.log.info("[下载] 开始：%s -> %s", chapter_url, save_dir)

        # 取图片直链
        img_urls = self.fetch_comic_images_by_parsing(chapter_url)
        if not img_urls:
            self.log.warning("[下载] 未获取到图片：%s", chapter_url)
            return

        # 多线程保存
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": referer or chapter_url,
        }

        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futures = []
            for idx, u in enumerate(img_urls, 1):
                out_path = os.path.join(save_dir, f"{idx:03d}.JPG")
                futures.append(ex.submit(self._download_one_image, u, out_path, headers))
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    self.log.error("[下载] 子任务异常：%s", e)

        self.log.info("[下载] 完成：%s | 共 %d 张", folder_name, len(img_urls))

    def _download_one_image(self, url: str, out_path: str, headers: Dict[str, str]) -> None:
        """
        下载单张图片，必要时转存为 JPG（quality=100），含重试。
        """
        if os.path.exists(out_path):
            self.log.debug("[跳过] 已存在：%s", out_path)
            return

        sess = self._requests_session_from_selenium(self.driver)
        for attempt in range(1, self.retries + 1):
            try:
                r = sess.get(url, headers=headers, timeout=self.timeout, stream=True)
                r.raise_for_status()
                content = r.content

                # 识别格式并转 JPG
                fmt = self._guess_ext_from_url_or_headers(url, r.headers)
                if fmt in (".jpg", ".jpeg"):
                    with open(out_path, "wb") as f:
                        f.write(content)
                else:
                    im = Image.open(io.BytesIO(content)).convert("RGB")
                    im.save(out_path, format="JPEG", quality=self.jpg_quality, optimize=True)

                self.log.debug("[保存] %s <- %s", out_path, url)
                return
            except Exception as e:
                self.log.warning("[重试 %d/%d] 下载失败：%s | %s", attempt, self.retries, url, e)
                time.sleep(0.6)
        self.log.error("[失败] 放弃：%s", url)

    @staticmethod
    def _guess_ext_from_url_or_headers(url: str, headers: Dict[str, str]) -> str:
        path = urlparse(url).path.lower()
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            if path.endswith(ext):
                return ext
        ct = headers.get("Content-Type", "").lower()
        if "jpeg" in ct:
            return ".jpg"
        if "png" in ct:
            return ".png"
        if "webp" in ct:
            return ".webp"
        return ".jpg"

    # -------------------------- Selenium/requests/工具函数（来自章节代码的实现，尽量不改动，仅加日志） --------------------------
    @staticmethod
    def _build_comic_url(comic_id: str) -> str:
        return f"https://www.kuaikanmanhua.com/web/comic/{comic_id}"

    @staticmethod
    def _load_cookies_from_file(cookie_json_path: str) -> List[Dict[str, Any]]:
        with open(cookie_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "cookies" in data:
            cookies = data["cookies"]
        elif isinstance(data, list):
            cookies = data
        else:
            raise ValueError("不识别的 cookies JSON 格式，请确认文件内容。")
        if not isinstance(cookies, list):
            raise ValueError("cookies 应为列表。")
        return cookies

    def _build_driver(self, chrome_binary_path: str, chromedriver_path: str, headless: bool = False) -> webdriver.Chrome:
        options = Options()
        options.binary_location = chrome_binary_path
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1400,900")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.page_load_strategy = "eager"
        service = Service(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        })
        return driver

    @staticmethod
    def _extract_topic_id(topic_url: str) -> Optional[str]:
        m = re.search(r"/topic/(\d+)", topic_url)
        return m.group(1) if m else None

    @staticmethod
    def _requests_session_from_selenium(driver: webdriver.Chrome) -> requests.Session:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.kuaikanmanhua.com/"
        })
        for c in driver.get_cookies():
            name, value = c.get("name"), c.get("value")
            if name and value:
                s.cookies.set(name, value, domain=c.get("domain") or ".kuaikanmanhua.com", path=c.get("path") or "/")
        return s

    @staticmethod
    def _extract_episode_no_from_title(title: str) -> Optional[int]:
        if not title:
            return None
        m = re.search(r"第\s*([0-9０-９一二三四五六七八九十百千]+)\s*话", title)
        if not m:
            return None
        raw = m.group(1)
        trans = str.maketrans("０１２３４５６７８９", "0123456789")
        raw = raw.translate(trans)
        if re.fullmatch(r"\d+", raw):
            try:
                return int(raw)
            except Exception:
                return None
        cnmap = {"零":0,"一":1,"二":2,"两":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9}
        unit = {"十":10,"百":100,"千":1000}
        total, num = 0, 0
        has_unit = False
        for ch in raw:
            if ch in cnmap:
                num = cnmap[ch]
                has_unit = True
            elif ch in unit:
                total += (num or 1) * unit[ch]
                num = 0
                has_unit = True
            else:
                return None
        total += num
        return total if has_unit else None

    @staticmethod
    def _try_fetch_from_nuxt_state(driver) -> Optional[List[Dict[str, Any]]]:
        try:
            nuxt = driver.execute_script("return window.__NUXT__ || window.__nuxt__ || null;")
            if not nuxt:
                return None
            candidates = []
            def walk(o):
                if isinstance(o, dict):
                    for k in ("comics", "comicList", "list", "items"):
                        if k in o and isinstance(o[k], list):
                            candidates.append(o[k])
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)
            walk(nuxt)

            #取章节信息
            out = []
            if not candidates:
                return None
            arr = candidates[0]
            for it in arr:
                if not isinstance(it, dict):
                    continue
                cid = it.get("id") or it.get("comic_id") or it.get("cid")
                title = it.get("title") or it.get("name") or ""
                epno = it.get("chapter_num") or it.get("episode_no") or it.get("no") or it.get("index")
                if not cid and isinstance(it.get("link"), str):
                    m = re.search(r"/comic/(\d+)", it["link"])
                    if m:
                        cid = m.group(1)
                if cid:
                    out.append({"id": str(cid), "title": str(title), "episode_no": epno})

            return out or None
        except Exception:
            return None

    def _try_fetch_by_api(self, driver, topic_id: str, limit: int = 60) -> Optional[List[Dict[str, Any]]]:
        s = self._requests_session_from_selenium(driver)
        endpoint_patterns = [
            "https://api.kkmh.com/v2/pweb/topic/{id}/comics",
            "https://api.kkmh.com/v2/pweb/topic/{id}",
            "https://api.kkmh.com/v1/pweb/topic/{id}/comics",
            "https://api.kkmh.com/v1/pweb/topic/{id}",
            "https://gateway.kuaikanmanhua.com/v2/pweb/topic/{id}/comics",
            "https://gateway.kuaikanmanhua.com/v1/pweb/topic/{id}/comics",
            "https://app.api.kuaikanmanhua.com/v2/pweb/topic/{id}/comics",
        ]
        for ep in endpoint_patterns:
            base_url = ep.format(id=topic_id)
            all_items, cursor, tried = [], None, 0
            try:
                while True:
                    params = {"limit": limit}
                    if cursor is not None:
                        params["since"] = cursor
                    r = s.get(base_url, params=params, timeout=15)
                    if r.status_code == 404:
                        break
                    r.raise_for_status()
                    try:
                        j = r.json()
                    except Exception:
                        break
                    data = (j.get("data") if isinstance(j, dict) else None) or j
                    if not isinstance(data, (dict, list)):
                        break
                    items = []
                    if isinstance(data, dict):
                        items = data.get("comics") or data.get("list") or data.get("items") or []
                    elif isinstance(data, list):
                        items = data
                    if not isinstance(items, list):
                        items = []
                    all_items.extend(items)
                    next_cursor = None
                    has_more = None
                    if isinstance(data, dict):
                        next_cursor = data.get("next_since") or data.get("next") or data.get("since")
                        has_more = data.get("has_more")
                    tried += 1
                    if (not next_cursor and not has_more) or len(items) == 0 or tried > 200:
                        break
                    cursor = next_cursor
                    time.sleep(0.2)
                if all_items:
                    out = []
                    for it in all_items:
                        cid = it.get("id") or it.get("comic_id")
                        title = it.get("title") or it.get("name") or ""
                        epno = it.get("chapter_num") or it.get("episode_no") or it.get("no") or it.get("index")
                        if cid:
                            out.append({"id": str(cid), "title": str(title), "episode_no": epno})
                    return out
            except Exception:
                continue
        return None

    @staticmethod
    def _scroll_to_load_all_chapters(driver, topic_url: str, max_rounds: int = 240) -> None:
        driver.get(topic_url)
        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        time.sleep(1)
        try:
            tab = driver.find_elements(By.XPATH, "//*/text()[contains(., '目录') or contains(., '全部章节')]/parent::*")
            for t in tab:
                try:
                    if t.is_displayed() and t.is_enabled():
                        t.click()
                        time.sleep(0.6)
                        break
                except Exception:
                    pass
        except Exception:
            pass
        possible_containers = [
            ".catalog", ".chapter-list", ".chapterList", ".TopicDetail",
            "[class*='catalog']", "[class*='chapter-list']", "[class*='Chapter']",
            ".list", ".List", ".chapters"
        ]
        container = None
        for sel in possible_containers:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el and el.size.get("height", 0) > 0:
                    container = el
                    break
            except Exception:
                continue
        last_count, same_count_rounds = 0, 0
        for _ in range(max_rounds):
            try:
                more_elems = driver.find_elements(
                    By.XPATH,
                    "//*[self::button or self::a or self::div or self::span]"
                    "[contains(., '展开全部') or contains(., '展开') or contains(., '更多') or "
                    " contains(., '查看更多') or contains(., '加载更多') or contains(., '更多章节')]"
                )
                for e in more_elems:
                    try:
                        if e.is_displayed() and e.is_enabled():
                            driver.execute_script("arguments[0].click();", e)
                            time.sleep(0.6)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                if container:
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", container)
                else:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.8)
            links = driver.find_elements(By.XPATH, "//a[contains(@href, '/comic/')]")
            count = len(links)
            same_count_rounds = same_count_rounds + 1 if count == last_count else 0
            last_count = count
            if same_count_rounds >= 3:
                break

    @staticmethod
    def _parse_chapters_from_dom(driver) -> List[Dict[str, Any]]:
        elems = driver.find_elements(By.XPATH, "//a[contains(@href, '/comic/')]")
        seen, out = set(), []
        for a in elems:
            try:
                href = a.get_attribute("href") or ""
                m = re.search(r"/comic/(\d+)", href)
                if not m:
                    continue
                cid = m.group(1)
                if cid in seen:
                    continue
                seen.add(cid)
                title = (a.get_attribute("title") or a.text or "").strip()
                if len(title) < 2:
                    try:
                        parent_text = a.find_element(By.XPATH, "ancestor-or-self::*[1]").text.strip()
                        if len(parent_text) > len(title):
                            title = parent_text
                    except Exception:
                        pass
                epno = None
                mm = re.search(r"第\s*([0-9０-９一二三四五六七八九十百千]+)\s*话", title)
                if mm:
                    epno = mm.group(1)
                out.append({"id": cid, "title": title, "episode_no": epno})
            except Exception:
                continue
        return out


    # -------------------------- 小工具 --------------------------
    @staticmethod
    def _safe_name(name: str) -> str:
        return re.sub(r'[\\/:*?"<>|]+', "_", (name or "").strip())


# ================================ MAIN 演示 ================================
if __name__ == "__main__":
    # 按你的环境修改
    chrome_binary_path = r"D:\python_contoon\chrome-win64\chrome.exe"
    chromedriver_path = r"D:\python_contoon\chromedriver-win64\chromedriver.exe"
    cookie_json_path = r"D:\python_contoon\kuikan\kuaikanmanhua.json"
    topic_url = "https://www.kuaikanmanhua.com/web/topic/12432/"
    log_file = r"D:\python_contoon\kuikan\kuaikan.log"

    client = KuaikanClient(
        chrome_binary_path=chrome_binary_path,
        chromedriver_path=chromedriver_path,
        cookie_json_path=cookie_json_path,
        save_root=r"E:/kuaikan",
        max_workers=8,
        jpg_quality=100,
        retries=3,
        timeout=20,
        headless=True,
        log_file=log_file,
    )

    ok, msg, title, driver = client.login(topic_url)
    if not ok:
        print("未检测到登录态，可能影响章节/图片访问。")

    # 获取章节（核心逻辑：NUXT -> API -> DOM）
    page_title, chapters = client.fetch_chapters(topic_url)
    print(f"[标题] {page_title} | [章节总数] {len(chapters)}")


    # # —— 选择性下载示例 ——
    # # 1) 用字符串表达式选择：如 "1-5,8,12-15"
    select_spec = "685"       # 自己改
    ranges = client.parse_select_spec(select_spec)
    to_download = client.filter_by_ranges(chapters, ranges)

    #
    # # 2) 或者你也可以直接整段下载（把上面两行换成：to_download = chapters）
    #
    print(f"[筛选] 计划下载 {len(to_download)} 条 | 条件：{select_spec}")
    for ch in to_download:
        client.download_chapter(page_title, ch)
