# core/adapters/dumawu_adapter.py
from __future__ import annotations
from typing import Dict, Any, Callable, List, Optional
from .dumawu_client import DumawuClient
import time

class DumawuAdapter:
    name = "读漫屋"

    def __init__(self, cfg):
        self.cfg = cfg
        self.client: Optional[DumawuClient] = None

    def build(self):
        if not self.client:
            self.client = DumawuClient(
                save_root=self.cfg.get("save_root"),
                max_workers=self.cfg.get("max_workers", 6),
                jpg_quality=self.cfg.get("jpg_quality", 95),
                retries=self.cfg.get("retries", 3),
                timeout=self.cfg.get("timeout", 20),
                headless=self.cfg.get("headless", True),
                chrome_path=self.cfg.get("chrome_path"),
                chromedriver_path=self.cfg.get("chromedriver_path"),
                log_file=None,
            )
        return self.client

    def login(self, topic_url: str):
        client = self.build()
        try:
            import requests
            r = requests.get(topic_url, headers={"User-Agent": "Mozilla/5.0 (Linux; Android 12) Mobile"})
            r.raise_for_status()
            detail = client.get_detail(r.text, topic_url)
            return True, "public site - no login required", detail.get("title", "")
        except Exception as e:
            return False, f"failed to fetch detail: {e}", ""

    def fetch_chapters(self, topic_url: str):
        client = self.build()
        import requests
        r = requests.get(topic_url, headers={"User-Agent": "Mozilla/5.0 (Linux; Android 12) Mobile"})
        r.raise_for_status()
        detail = client.get_detail(r.text, topic_url)
        chapters = detail.get("chapters", [])
        for i, ch in enumerate(chapters, 1):
            ch.setdefault("order", ch.get("order", i))
            ch.setdefault("title", ch.get("title", ""))
            ch.setdefault("id", ch.get("id", ""))
            ch.setdefault("url", ch.get("url", ""))
        return detail.get("title", ""), chapters

    def download_chapter_with_progress(self, topic_title: str, chapter: Dict[str, Any],
                                       on_progress: Callable[[int,int],None]=None,
                                       on_error: Callable[[str],None]=None) -> bool:
        client = self.build()
        import requests
        try:
            r = requests.get(chapter.get("url"), headers={"User-Agent": "Mozilla/5.0 (Linux; Android 12) Mobile"})
            r.raise_for_status()
            html = r.text
        except Exception as e:
            if self.cfg.get("chromedriver_path") and self.cfg.get("headless", True):
                client.log.info("requests failed for chapter, trying selenium fallback: %s", e)
                try:
                    if not client.driver:
                        client.driver = client._build_driver()
                    client.driver.get(chapter.get("url"))
                    time.sleep(0.8)
                    html = client.driver.page_source
                except Exception as se:
                    if on_error: on_error(f"failed to load chapter page: {se}")
                    return False
            else:
                if on_error: on_error(f"failed to load chapter page: {e}")
                return False

        image_urls = client.get_chapter_images(html, chapter.get("url"), use_selenium_fallback=False)
        if not image_urls and self.cfg.get("chromedriver_path"):
            image_urls = client.get_chapter_images(html, chapter.get("url"), use_selenium_fallback=True)
        return client.download_images(topic_title, chapter, image_urls, on_progress, on_error)