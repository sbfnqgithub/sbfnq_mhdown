
from __future__ import annotations
from typing import List, Dict, Any
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QWaitCondition, QMutex

class DownloadWorker(QThread):
    sigChapterStarted = pyqtSignal(dict)
    sigProgress = pyqtSignal(int, int, int)      # chapter_idx, done_pages, total_pages
    sigChapterDone = pyqtSignal(int)
    sigChapterFailed = pyqtSignal(int, str)
    sigLog = pyqtSignal(str)
    sigAllDone = pyqtSignal()

    def __init__(self, adapter, topic_title: str, chapters: List[Dict[str,Any]]):
        super().__init__()
        self.adapter = adapter
        self.topic_title = topic_title
        self.chapters = chapters
        self._paused = False
        self._cancelled = False
        self._cond = QWaitCondition()
        self._mutex = QMutex()

    def pause(self):
        self._mutex.lock()
        self._paused = True
        self._mutex.unlock()
        self.sigLog.emit("已暂停")

    def resume(self):
        self._mutex.lock()
        self._paused = False
        self._cond.wakeAll()
        self._mutex.unlock()
        self.sigLog.emit("继续下载")

    def cancel(self):
        self._mutex.lock()
        self._cancelled = True
        self._cond.wakeAll()
        self._mutex.unlock()
        self.sigLog.emit("取消任务中…")

    def _check_pause_or_cancel(self):
        self._mutex.lock()
        try:
            if self._cancelled:
                return False
            while self._paused and not self._cancelled:
                self._cond.wait(self._mutex, 200)
            return not self._cancelled
        finally:
            self._mutex.unlock()

    def run(self):
        for idx, ch in enumerate(self.chapters):
            if not self._check_pause_or_cancel():
                break
            self.sigChapterStarted.emit(ch)
            def on_progress(done, total):
                self.sigProgress.emit(idx, done, total)
                self._check_pause_or_cancel()
            def on_error(msg):
                self.sigLog.emit(f"[错误] {msg}")
            ok = self.adapter.download_chapter_with_progress(self.topic_title, ch, on_progress, on_error)
            if ok:
                self.sigChapterDone.emit(idx)
            else:
                self.sigChapterFailed.emit(idx, "下载失败")
        self.sigAllDone.emit()
