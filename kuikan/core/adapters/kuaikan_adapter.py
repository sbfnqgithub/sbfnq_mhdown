
from __future__ import annotations
from typing import List, Dict, Any, Optional, Callable
import os, sys

# Add search paths for user's kuikan_img.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

try:
    from kuikan_img import KuaikanClient
except Exception:
    from kuikan_img import KuaikanClient  # adjust if needed

class KuaikanAdapter:
    name = "快看漫画"
    def __init__(self, cfg):
        self.cfg = cfg
        self.client: Optional[KuaikanClient] = None

    def build(self):
        self.client = KuaikanClient(
            chrome_binary_path=self.cfg.chrome_path,
            chromedriver_path=self.cfg.chromedriver_path,
            cookie_json_path=self.cfg.cookie_path,
            save_root=self.cfg.save_root,
            max_workers=self.cfg.max_workers,
            jpg_quality=self.cfg.jpg_quality,
            retries=self.cfg.retries,
            timeout=self.cfg.timeout,
            headless=self.cfg.headless,
            log_file=None,
        )
        return self.client

    def login(self, topic_url: str):
        if not self.client:
            self.build()
        ok, msg, title, _ = self.client.login(topic_url)
        return ok, msg, title

    def fetch_chapters(self, topic_url: str):
        assert self.client is not None
        title, chapters = self.client.fetch_chapters(topic_url)
        for ch in chapters:
            ch.setdefault("order", 0)
            ch.setdefault("title", "")
            ch.setdefault("id", "")
            ch.setdefault("url", self.client._build_comic_url(str(ch.get("id"))))
        return title, chapters

    def download_chapter_with_progress(self, topic_title: str, chapter: Dict[str, Any],
                                       on_progress: Callable[[int,int],None]|None=None,
                                       on_error: Callable[[str],None]|None=None) -> bool:
        assert self.client is not None
        chapter_url = chapter.get("url")
        try:
            urls = self.client.fetch_comic_images_by_parsing(chapter_url)
        except Exception as e:
            if on_error: on_error(f"获取图片失败: {e}")
            return False
        total = len(urls)
        if total == 0:
            if on_error: on_error("无图片")
            return False
        order = chapter.get("order", 0)
        chap_title = (chapter.get("title") or "").strip().replace("\n", " ")
        folder_name = f"{order:03d}  {chap_title}".strip()
        save_dir = os.path.join(self.client.save_root, self.client._safe_name(topic_title), self.client._safe_name(folder_name))
        os.makedirs(save_dir, exist_ok=True)
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": chapter_url,
        }
        done = 0
        for idx, u in enumerate(urls, 1):
            out_path = os.path.join(save_dir, f"{idx:03d}.JPG")
            try:
                self.client._download_one_image(u, out_path, headers)
                done += 1
                if on_progress:
                    on_progress(done, total)
            except Exception as e:
                if on_error:
                    on_error(str(e))
        return True
