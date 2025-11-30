# core/adapters/dumawu_client.py
# Dumawu client for 读漫屋 (Dumawu) - synchronous implementation with Selenium fallback
from __future__ import annotations
import os
import time
import io
import logging
from typing import List, Dict, Any, Callable, Optional
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from PIL import Image

# Selenium is optional; used only as a fallback when JS must run to produce image URLs
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    SELENIUM_AVAILABLE = True
except Exception:
    SELENIUM_AVAILABLE = False

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 12; Pixel 6) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
)

def setup_logger(name="dumawu", log_file: Optional[str]=None, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] - %(message)s", "%H:%M:%S"))
        logger.addHandler(sh)
        if log_file:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] - %(message)s", "%H:%M:%S"))
            logger.addHandler(fh)
    return logger

class DumawuClient:
    def __init__(
        self,
        save_root: str,
        max_workers: int = 6,
        jpg_quality: int = 95,
        retries: int = 3,
        timeout: int = 20,
        headless: bool = True,
        chrome_path: Optional[str] = None,
        chromedriver_path: Optional[str] = None,
        log_file: Optional[str] = None,
    ):
        self.save_root = save_root
        self.max_workers = max_workers
        self.jpg_quality = jpg_quality
        self.retries = retries
        self.timeout = timeout
        self.headless = headless
        self.chrome_path = chrome_path
        self.chromedriver_path = chromedriver_path

        os.makedirs(self.save_root, exist_ok=True)
        self.log = setup_logger("dumawu", log_file)
        self.driver = None

    def _requests_session(self):
        s = requests.Session()
        s.headers.update({
            "User-Agent": MOBILE_UA,
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        return s

    def _build_driver(self):
        if not SELENIUM_AVAILABLE:
            raise RuntimeError("Selenium not available")
        options = Options()
        if self.chrome_path:
            options.binary_location = self.chrome_path
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument(f"--user-agent={MOBILE_UA}")
        options.add_argument("--window-size=412,915")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        service = Service(executable_path=self.chromedriver_path) if self.chromedriver_path else Service()
        driver = webdriver.Chrome(service=service, options=options)
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            })
        except Exception:
            pass
        return driver

    def get_detail(self, detail_html: str, detail_url: str) -> Dict[str, Any]:
        """
        Parse detail page HTML to extract title, cover, and chapters.
        Enhanced Selenium fallback:
          - use WebDriverWait (显性等待)
          - try execute_script click on "更多"/"加载"按钮 by text and by common selectors
          - try repeated scrolls
          - detect chapter count increase and stop when stable
        Returns: {"title": str, "cover": str, "chapters": [ {order,title,url}, ... ] }
        """
        soup = BeautifulSoup(detail_html, "html.parser")
        title_node = soup.select_one("h1.banner-title, .banner-title, h1")
        title = title_node.get_text(strip=True) if title_node else ""
        cover = ""
        cover_node = soup.select_one(".cartoon-cover img, .cover img")
        if cover_node:
            cover = cover_node.get("src") or cover_node.get("data-src") or ""
            if cover and cover.startswith("/"):
                cover = urljoin(detail_url, cover)

        def parse_chapters_from_soup(soup_obj):
            nodes = soup_obj.select(
                ".chaplist-box ul li a, .chapter-list a, .chapters a, .chapter-item a, .chapter-list-item a")
            if not nodes:
                # fallback broader
                nodes = soup_obj.select("a")
            chapters_local = []
            seen = set()
            for a in nodes:
                href = a.get("href") or ""
                if not href or href.startswith("javascript:"):
                    continue
                absurl = href if href.startswith("http") else urljoin(detail_url, href)
                if absurl in seen:
                    continue
                seen.add(absurl)
                txt = a.get_text(strip=True) or "Chapter"
                chapters_local.append({"order": len(chapters_local) + 1, "title": txt, "url": absurl})
            return chapters_local

        chapters = parse_chapters_from_soup(soup)

        # If chapters small, try Selenium fallback with stronger strategy
        if len(chapters) < 30 and SELENIUM_AVAILABLE:
            try:
                self.log.info("章节数较少(%d)，尝试更强 Selenium 展开全部章节", len(chapters))
                # build driver with mobile emulation and headless according to settings
                opts = self._build_chrome_options() if hasattr(self, "_build_chrome_options") else None
                driver = None
                try:
                    # If we have a helper to build driver, use it, otherwise build minimal
                    if hasattr(self, "_build_driver"):
                        driver = self._build_driver()
                    else:
                        from selenium import webdriver
                        from selenium.webdriver.chrome.options import Options
                        chrome_options = Options()
                        # try to emulate mobile for consistent UI
                        try:
                            chrome_options.add_experimental_option("mobileEmulation", {"deviceName": "Pixel 5"})
                        except Exception:
                            pass
                        if hasattr(self, "s") and getattr(self.s, "headless", True):
                            chrome_options.add_argument("--headless=new")
                        chrome_options.add_argument("--no-sandbox")
                        chrome_options.add_argument("--disable-dev-shm-usage")
                        driver = webdriver.Chrome(executable_path=getattr(self.s, "chromedriver_path", None),
                                                  options=chrome_options)

                    from selenium.webdriver.common.by import By
                    from selenium.webdriver.support.ui import WebDriverWait
                    from selenium.webdriver.support import expected_conditions as EC

                    driver.set_page_load_timeout(getattr(self.s, "timeout", 20))
                    driver.get(detail_url)
                    wait = WebDriverWait(driver, getattr(self.s, "timeout", 20))

                    # Wait for chapter container or at least any link to appear
                    try:
                        wait.until(EC.presence_of_element_located(
                            (By.CSS_SELECTOR, ".chaplist-box, .chapter-list, .chapters, .chapter-item")))
                    except Exception:
                        # still proceed, maybe selectors differ
                        pass

                    # Try multiple strategies to reveal all chapters
                    def try_click_more_once():
                        clicked_any = False
                        # 1) try by visible text
                        for txt in ["更多话", "更多章节", "更多", "展开全部", "加载全部", "显示全部"]:
                            try:
                                els = driver.find_elements("xpath", f"//*[contains(text(), '{txt}')]")
                                for el in els:
                                    try:
                                        driver.execute_script("arguments[0].scrollIntoView(true);", el)
                                        driver.execute_script("arguments[0].click();", el)
                                        clicked_any = True
                                        time.sleep(0.6)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        # 2) try by common class names/selectors
                        for sel in [".load-more", ".more-chapters", ".show-more", ".open-all", ".chapter-more",
                                    ".more-btn"]:
                            try:
                                els = driver.find_elements("css selector", sel)
                                for el in els:
                                    try:
                                        driver.execute_script("arguments[0].scrollIntoView(true);", el)
                                        driver.execute_script("arguments[0].click();", el)
                                        clicked_any = True
                                        time.sleep(0.6)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        return clicked_any

                    # initial parse
                    last_count = 0
                    stable_rounds = 0
                    # Try up to N loops: click more, then scroll bottom to trigger lazy loads
                    for attempt in range(8):
                        page_src = driver.page_source
                        soup_now = BeautifulSoup(page_src, "html.parser")
                        parsed = parse_chapters_from_soup(soup_now)
                        cur_count = len(parsed)
                        # if count increases, reset stable counter
                        if cur_count > last_count:
                            last_count = cur_count
                            stable_rounds = 0
                        else:
                            stable_rounds += 1

                        # If we already have many chapters, break early
                        if cur_count >= 50:
                            chapters = parsed
                            break

                        # Try clicking "more" controls
                        clicked = try_click_more_once()

                        # Scroll down several times to trigger lazy load
                        for _ in range(6):
                            driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                            time.sleep(0.4)

                        # short wait for AJAX content
                        time.sleep(0.8)

                        # if attempt didn't change content for several rounds, break
                        if stable_rounds >= 3:
                            # update chapters from last parsed
                            chapters = parsed
                            break
                    else:
                        # final parse once more
                        page_src = driver.page_source
                        soup_final = BeautifulSoup(page_src, "html.parser")
                        parsed = parse_chapters_from_soup(soup_final)
                        if len(parsed) > len(chapters):
                            chapters = parsed

                finally:
                    try:
                        if driver:
                            driver.quit()
                    except Exception:
                        pass

            except Exception as e:
                self.log.exception("Selenium 强化展开章节失败: %s", e)

        # final normalization: sort or keep as-is depending on site config (we keep discovered order)
        return {"title": title, "cover": cover, "chapters": chapters}

    def get_chapter_images(self, chapter_html: str, chapter_url: str, use_selenium_fallback: bool=False) -> List[str]:
        soup = BeautifulSoup(chapter_html, "html.parser")
        imgs = []
        selector = ".chapter-img-box img, .reader-img img, .comic-page img, img"
        for img in soup.select(selector):
            src = (img.get("src") or img.get("data-src") or img.get("data-original") or "").strip()
            if not src:
                continue
            if src.startswith("//"):
                src = "https:" + src
            if src.startswith("/"):
                src = urljoin(chapter_url, src)
            imgs.append(src)
        imgs = [u for u in imgs if u and not u.lower().endswith(("loading.gif","placeholder.png"))]
        if imgs:
            return imgs
        if use_selenium_fallback and SELENIUM_AVAILABLE:
            self.log.info("No imgs in static HTML; try selenium")
            driver = self._build_driver()
            try:
                driver.get(chapter_url)
                time.sleep(1.0)
                for _ in range(6):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(0.4)
                page = driver.page_source
                soup2 = BeautifulSoup(page, "html.parser")
                imgs2 = []
                for img in soup2.select(selector):
                    src = (img.get("src") or img.get("data-src") or img.get("data-original") or "").strip()
                    if not src:
                        continue
                    if src.startswith("//"):
                        src = "https:" + src
                    if src.startswith("/"):
                        src = urljoin(chapter_url, src)
                    imgs2.append(src)
                return imgs2
            finally:
                try: driver.quit()
                except Exception: pass
        return []

    def download_images(self, topic_title: str, chapter: Dict[str, Any],
                        image_urls: List[str],
                        on_progress: Optional[Callable[[int,int],None]] = None,
                        on_error: Optional[Callable[[str],None]] = None) -> bool:
        total = len(image_urls)
        if total == 0:
            if on_error: on_error("no images to download")
            return False
        order = chapter.get("order", 0)
        chap_title = (chapter.get("title") or "").strip().replace("\n", " ")
        folder_name = f"{order:03d}  {chap_title}".strip()
        save_dir = os.path.join(self.save_root, self._safe_name(topic_title), self._safe_name(folder_name))
        os.makedirs(save_dir, exist_ok=True)

        session = self._requests_session()
        headers = {"Referer": chapter.get("url") or ""}

        done = 0
        def fetch_and_save(url, idx):
            nonlocal done
            out_path = os.path.join(save_dir, f"{idx:03d}.JPG")
            if os.path.exists(out_path):
                return True
            for attempt in range(1, self.retries+1):
                try:
                    r = session.get(url, headers=headers, timeout=self.timeout, stream=True)
                    r.raise_for_status()
                    data = r.content
                    ct = r.headers.get("Content-Type", "").lower()
                    if url.lower().endswith((".jpg", ".jpeg")) or "jpeg" in ct:
                        with open(out_path, "wb") as f:
                            f.write(data)
                    else:
                        img = Image.open(io.BytesIO(data)).convert("RGB")
                        img.save(out_path, format="JPEG", quality=self.jpg_quality, optimize=True)
                    return True
                except Exception:
                    time.sleep(0.5)
            return False

        with ThreadPoolExecutor(max_workers=min(self.max_workers, 8)) as ex:
            futures = {ex.submit(fetch_and_save, u, i+1): i+1 for i,u in enumerate(image_urls)}
            for fut in as_completed(futures):
                idx = futures[fut]
                ok = False
                try:
                    ok = fut.result()
                except Exception as e:
                    if on_error: on_error(f"save error: {e}")
                if ok:
                    done += 1
                    if on_progress: on_progress(done, total)
                else:
                    if on_error: on_error(f"failed to save image idx={idx}")
        return True

    @staticmethod
    def _safe_name(name: str) -> str:
        return "".join(ch for ch in name if ch not in r'\/:*?"<>|').strip()[:200]