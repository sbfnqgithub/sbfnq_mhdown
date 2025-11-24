
from __future__ import annotations
import os, json, re
from dataclasses import dataclass
from typing import List, Dict, Optional

LIB_FILE = "library.json"

@dataclass
class Topic:
    site: str
    title: str
    topic_url: Optional[str] = None
    author: str = ""
    cover: str = ""
    save_dir: str = ""

@dataclass
class ChapterEntry:
    order: int
    title: str
    episode_no: Optional[str] = None
    url: str = ""
    downloaded_files: int = 0
    total_files: int = 0
    paid_flag: int = 0

class Library:
    def __init__(self, save_root: str, data_dir: str):
        self.save_root = save_root
        self.db_path = os.path.join(data_dir, LIB_FILE)
        self.data = {"topics": {}}
        if os.path.exists(self.db_path):
            try:
                self.data = json.load(open(self.db_path, "r", encoding="utf-8"))
            except Exception:
                pass

    def save(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        json.dump(self.data, open(self.db_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    def list_topics(self, site: str) -> List[Topic]:
        out: List[Topic] = []
        for k, v in self.data.get("topics", {}).items():
            if v.get("site") == site:
                out.append(Topic(**v))
        # also scan filesystem for missing
        site_root = os.path.join(self.save_root)
        if os.path.isdir(site_root):
            for title in os.listdir(site_root):
                p = os.path.join(site_root, title)
                if os.path.isdir(p):
                    key = f"{site}:{title}"
                    if key not in self.data["topics"]:
                        self.data["topics"][key] = dict(site=site, title=title, save_dir=p)
                        out.append(Topic(site=site, title=title, save_dir=p))
        return sorted(out, key=lambda t: t.title)

    def upsert_topic(self, site: str, title: str, topic_url: Optional[str], save_dir: str, author: str=""):
        key = f"{site}:{title}"
        self.data.setdefault("topics", {})
        self.data["topics"][key] = dict(site=site, title=title, topic_url=topic_url, save_dir=save_dir, author=author)
        self.save()

    def scan_chapters_local(self, site: str, title: str) -> Dict[str, ChapterEntry]:
        # Scan local folder to infer downloaded chapters and files count.
        base = os.path.join(self.save_root, title)
        result: Dict[str, ChapterEntry] = {}
        if not os.path.isdir(base):
            return result
        for name in os.listdir(base):
            fp = os.path.join(base, name)
            if not os.path.isdir(fp):
                continue
            # name like "001  第1话 标题"
            m = re.match(r"(\d+)", name.strip())
            order = int(m.group(1)) if m else 0
            files = [x for x in os.listdir(fp) if x.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
            result[name] = ChapterEntry(order=order, title=name, episode_no=None, url="", downloaded_files=len(files), total_files=max(len(files), 0))
        return result
    # —— 章列表缓存：仅当点击“同步章节”时才更新到这里 ——
    def set_topic_chapters(self, site: str, title: str, chapters: list[dict]):
        """把在线获取到的章节列表缓存到本地（只保存必要字段）"""
        key = f"{site}:{title}"
        self.data.setdefault("topics", {})
        t = self.data["topics"].setdefault(key, dict(site=site, title=title, save_dir=os.path.join(self.save_root, title)))
        # 最小化存储
        t["chapters"] = [
            {
                "order": c.get("order", 0),
                "episode_no": c.get("episode_no"),
                "title": c.get("title", ""),
                "url": c.get("url", ""),
            }
        for c in chapters]
        self.save()

    def get_topic_chapters(self, site: str, title: str) -> list[dict]:
        """读取本地缓存的章节列表；如果没有，就返回空列表"""
        key = f"{site}:{title}"
        t = self.data.get("topics", {}).get(key) or {}
        return t.get("chapters", []) or []

    def mark_chapters_downloaded(self, site: str, title: str, orders: list[int]):
        """把指定 order 的章节标记为已下载（影响 UI 过滤/隐藏）"""
        key = f"{site}:{title}"
        t = self.data.get("topics", {}).get(key)
        if not t:
            return
        # 给章节加一个 downloaded_files 计数（>=1 视为已下载）
        chs = t.get("chapters") or []
        for ch in chs:
            if int(ch.get("order", 0)) in {int(x) for x in orders}:
                ch["downloaded_files"] = max(1, int(ch.get("downloaded_files", 0)))
        self.save()
