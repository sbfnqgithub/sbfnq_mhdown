
from __future__ import annotations
import json, os
from dataclasses import dataclass, asdict

DEFAULTS = dict(
    save_root=r"E:/kuaikan",
    max_workers=8,
    jpg_quality=100,
    timeout=20,
    retries=3,
    headless=True,
    chrome_path=r"D:\python_contoon\chrome-win64\chrome.exe",
    chromedriver_path=r"D:\python_contoon\chromedriver-win64\chromedriver.exe",
    cookie_path=r"D:\python_contoon\kuikan\kuaikanmanhua.json",
    show_downloaded=False,
    allow_redownload=False,   # 允许重复下载（默认关闭；防误操作）

)

@dataclass
class AppSettings:
    save_root: str
    max_workers: int
    jpg_quality: int
    timeout: int
    retries: int
    headless: bool
    chrome_path: str
    chromedriver_path: str
    cookie_path: str
    show_downloaded: bool
    allow_redownload: bool

    @classmethod
    def load(cls, path: str) -> "AppSettings":
        if not os.path.exists(path):
            return cls(**DEFAULTS)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = {**DEFAULTS, **data}
        return cls(**merged)

    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
