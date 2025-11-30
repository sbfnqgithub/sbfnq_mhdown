# core/adapters/dumawu_utils.py
import os
def safe_name(name: str) -> str:
    return "".join(ch for ch in name if ch not in r'\\/:"*?<>|').strip()[:200]
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)
    return path