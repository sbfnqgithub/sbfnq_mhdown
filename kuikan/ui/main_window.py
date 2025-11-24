
import os
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QCheckBox, QPushButton, QLabel, QProgressBar, QPlainTextEdit, QMessageBox)
from PyQt6.QtCore import Qt
from core.settings import AppSettings
from core.library import Library
from core.adapters.kuaikan_adapter import KuaikanAdapter
from core.controller import DownloadWorker
from ui.settings_dialog import SettingsDialog

class MainWindow(QMainWindow):
    def __init__(self, settings_path: str, data_dir: str):
        super().__init__()
        self.setWindowTitle("漫画下载器 - 暗色版")
        self.settings_path = settings_path
        self.data_dir = data_dir
        self.s = AppSettings.load(settings_path)
        self.lib = Library(self.s.save_root, data_dir)
        self.adapter = KuaikanAdapter(self.s)
        self.current_topic = None
        self.current_chapters = []
        self.worker: DownloadWorker|None = None
        self._block_item_changed = False



        header = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("搜索：我的漫画库 / 章节标题")
        self.toggleShowAll = QCheckBox("显示已下载")
        self.toggleShowAll.setChecked(self.s.show_downloaded)
        btnSettings = QPushButton("设置")
        header.addWidget(QLabel("站点：快看"))
        header.addWidget(self.search, 1)
        header.addWidget(self.toggleShowAll)
        header.addWidget(btnSettings)

        btnAddTopic = QPushButton("新增漫画")
        btnSetUrl = QPushButton("设置URL")
        header.addWidget(btnAddTopic)
        header.addWidget(btnSetUrl)

        self.libraryList = QListWidget()
        self.refresh_library()

        self.chapterTable = QTableWidget(0, 7)
        self.chapterTable.setHorizontalHeaderLabels(["选", "序号", "话数", "标题", "状态", "进度", "错误信息"])
        self.chapterTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.chapterTable.setSelectionBehavior(self.chapterTable.SelectionBehavior.SelectRows)
        self.chapterTable.setEditTriggers(self.chapterTable.EditTrigger.NoEditTriggers)

        self.chapterTable.itemChanged.connect(self.on_item_changed)
        controls = QHBoxLayout()
        self.btnFetch = QPushButton("同步章节")  # 点击才联网更新并缓存
        self.btnSelectAll = QPushButton("全选")  # ← 新增
        self.btnSelectNone = QPushButton("全不选")  # ← 新增
        self.btnMarkDownloaded = QPushButton("标记为已下载")  # ← 新增（会隐藏）

        self.btnStart = QPushButton("开始下载")
        self.btnPause = QPushButton("暂停")
        self.btnResume = QPushButton("继续")
        self.btnCancel = QPushButton("取消")
        self.btnPause.setEnabled(False)
        self.btnResume.setEnabled(False)
        self.btnCancel.setEnabled(False)

        # 排列一下：同步/全选/全不选/标记 → 开始/暂停/继续/取消
        controls.addWidget(self.btnFetch)
        controls.addWidget(self.btnSelectAll)
        controls.addWidget(self.btnSelectNone)
        controls.addWidget(self.btnMarkDownloaded)
        controls.addStretch(1)
        controls.addWidget(self.btnStart)
        controls.addWidget(self.btnPause)
        controls.addWidget(self.btnResume)
        controls.addWidget(self.btnCancel)

        self.totalProgress = QProgressBar()
        self.totalLabel = QLabel("就绪")
        self.logView = QPlainTextEdit(); self.logView.setReadOnly(True)

        right = QWidget(); rlay = QVBoxLayout(right)
        rlay.addLayout(controls)
        rlay.addWidget(self.chapterTable, 3)
        rlay.addWidget(self.totalProgress)
        rlay.addWidget(self.totalLabel)
        rlay.addWidget(self.logView, 2)

        splitter = QSplitter()
        left = QWidget(); ll = QVBoxLayout(left); ll.addWidget(QLabel("我的漫画库")); ll.addWidget(self.libraryList)
        splitter.addWidget(left); splitter.addWidget(right); splitter.setStretchFactor(1, 3)

        root = QWidget(); rootLay = QVBoxLayout(root); rootLay.addLayout(header); rootLay.addWidget(splitter)
        self.setCentralWidget(root)

        btnSettings.clicked.connect(self.open_settings)
        self.btnSelectAll.clicked.connect(self.select_all_rows)
        self.btnSelectNone.clicked.connect(self.select_none_rows)
        self.btnMarkDownloaded.clicked.connect(self.mark_selected_as_downloaded)
        self.libraryList.itemDoubleClicked.connect(self.pick_topic_from_library)
        self.btnFetch.clicked.connect(self.sync_chapters_clicked)
        self.btnStart.clicked.connect(self.start_download_clicked)
        self.btnPause.clicked.connect(self.pause_clicked)
        self.btnResume.clicked.connect(self.resume_clicked)
        self.btnCancel.clicked.connect(self.cancel_clicked)
        self.search.textChanged.connect(self.apply_filters)
        self.toggleShowAll.stateChanged.connect(self.apply_filters)

        btnAddTopic.clicked.connect(self.add_topic_dialog)
        btnSetUrl.clicked.connect(self.set_topic_url_dialog)

    def log(self, text: str):
        self.logView.appendPlainText(text)

    def refresh_library(self):
        self.libraryList.clear()
        topics = self.lib.list_topics("kuaikan")
        keyword = self.search.text().strip().lower()
        for t in topics:
            if keyword and keyword not in t.title.lower():
                continue
            item = QListWidgetItem(f"{t.title}")
            item.setData(Qt.ItemDataRole.UserRole, t)
            self.libraryList.addItem(item)

    def pick_topic_from_library(self, item: QListWidgetItem):
        """双击左侧漫画标题时，从本地缓存加载章节"""
        t = item.data(Qt.ItemDataRole.UserRole)
        self.current_topic = t
        self.log(f"已选择：{t.title}")

        # 切换漫画时：自动关闭“允许重复下载”防误操作
        if self.s.allow_redownload:
            self.s.allow_redownload = False
            self.s.save(self.settings_path)
            self.log("已自动关闭『允许重复下载』，如需再次重复下载请到设置里重新勾选。")

        # 清空章节表格
        table = self.chapterTable
        table.setSortingEnabled(False)  # 禁止排序
        table.blockSignals(True)
        table.setUpdatesEnabled(False)
        table.clearContents()
        table.setRowCount(0)

        # 从缓存加载章节
        cached = self.lib.get_topic_chapters("kuaikan", t.title)
        if cached:
            for ch in cached:  # 不再排序，保持原顺序
                downloaded_files = int(ch.get("downloaded_files", 0))
                row_ch = dict(
                    order=ch.get("order"),
                    episode_no=ch.get("episode_no"),
                    title=ch.get("title"),
                    url=ch.get("url"),
                    downloaded_files=downloaded_files,
                    total_files=0
                )
                self._append_chapter_row(row_ch)
        else:
            QMessageBox.information(self, "提示", "该漫画还没有本地缓存，请点击『同步章节』以从服务器更新。")

        # 重新启用更新
        table.setUpdatesEnabled(True)
        table.blockSignals(False)
        table.setSortingEnabled(False)
        self.apply_filters()

    def populate_chapters_cached_or_local(self, title: str):
        self.chapterTable.setRowCount(0)
        cached = self.lib.get_topic_chapters("kuaikan", title)
        if cached:
            # 使用本地缓存的章节清单
            for ch in sorted(cached, key=lambda x: int(x.get("order", 0))):
                downloaded_files = int(ch.get("downloaded_files", 0))
                row_ch = dict(order=ch.get("order"), episode_no=ch.get("episode_no"), title=ch.get("title"),
                              url=ch.get("url"), downloaded_files=downloaded_files, total_files=0)
                self._append_chapter_row(row_ch)
        else:
            # 回退：只根据本地已下载的目录来展示
            local = self.lib.scan_chapters_local("kuaikan", title)
            for name, entry in sorted(local.items(), key=lambda kv: kv[1].order):
                self._append_chapter_row(dict(order=entry.order, episode_no="", title=name, url="",
                                              downloaded_files=entry.downloaded_files, total_files=entry.total_files))
        self.apply_filters()

    def _append_chapter_row(self, ch: dict):
        row = self.chapterTable.rowCount()
        self.chapterTable.insertRow(row)

        chk = QTableWidgetItem("")
        downloaded = ch.get("downloaded_files", 0) > 0
        # 未下载默认勾选；已下载默认不勾选
        chk.setCheckState(Qt.CheckState.Checked if not downloaded else Qt.CheckState.Unchecked)
        self.chapterTable.setItem(row, 0, chk)

        # 序号（按整数排序）
        order_val = int(ch.get("order", 0) or 0)
        it_order = QTableWidgetItem(str(order_val))
        it_order.setData(Qt.ItemDataRole.DisplayRole, order_val)  # ← 让 Qt 知道这是数字
        self.chapterTable.setItem(row, 1, it_order)

        # 话数（如果有数字也按整数，否则保留字符串）
        epraw = ch.get("episode_no", None)
        try:
            ep_val = int(epraw)
            it_ep = QTableWidgetItem(str(ep_val))
            it_ep.setData(Qt.ItemDataRole.DisplayRole, ep_val)  # ← 也是数字
        except (TypeError, ValueError):
            it_ep = QTableWidgetItem(str(epraw or ""))
        self.chapterTable.setItem(row, 2, it_ep)

        self.chapterTable.setItem(row, 3, QTableWidgetItem(ch.get("title", "")))
        self.chapterTable.setItem(row, 4, QTableWidgetItem("已存在" if downloaded else "待开始"))

        prog = QTableWidgetItem("0/0")
        prog.setData(Qt.ItemDataRole.UserRole, 0)
        prog.setData(Qt.ItemDataRole.UserRole + 1, 0)
        self.chapterTable.setItem(row, 5, prog)
        self.chapterTable.setItem(row, 6, QTableWidgetItem(""))

        # 存原始数据
        self.chapterTable.item(row, 0).setData(Qt.ItemDataRole.UserRole, ch)

        # 下载过且未开启“允许重复下载” → 该行“选框”不可用（但仍可看见）
        if downloaded and not self.s.allow_redownload:
            flags = self.chapterTable.item(row, 0).flags()
            self.chapterTable.item(row, 0).setFlags(flags & ~Qt.ItemFlag.ItemIsEnabled)

    def sync_chapters_clicked(self):
        """从服务器同步最新章节列表"""
        if not self.current_topic or not self.current_topic.topic_url:
            QMessageBox.warning(self, "提示", "请先在左侧选择含有 URL 的漫画条目（或手工在设置中配置后登录一次保存）。")
            return

        ok, msg, title = self.adapter.login(self.current_topic.topic_url)
        self.log(f"[登录] {msg}")
        t, chapters = self.adapter.fetch_chapters(self.current_topic.topic_url)
        self.current_chapters = chapters

        table = self.chapterTable
        # —— 批量填充前：关闭排序/信号/重绘 ——
        table.setSortingEnabled(False)
        table.blockSignals(True)
        table.setUpdatesEnabled(False)
        table.clearContents()
        table.setRowCount(0)

        # 合并本地“已下载”状态
        local = self.lib.scan_chapters_local("kuaikan", title)

        def downloaded_files_for(ch: dict) -> int:
            """查找本地已下载文件数量"""
            for name, entry in local.items():
                if name.startswith(f"{ch.get('order', 0):03d}"):
                    return entry.downloaded_files
            return 0

        # 不再排序，保持服务器返回的原始顺序
        for ch in chapters:
            row_ch = dict(
                order=ch.get("order"),
                episode_no=ch.get("episode_no"),
                title=ch.get("title"),
                url=ch.get("url"),
                downloaded_files=downloaded_files_for(ch),
                total_files=0
            )
            self._append_chapter_row(row_ch)  # 内部不再调用 sortItems

        # —— 批量结束：恢复界面刷新 ——
        table.setUpdatesEnabled(True)
        table.blockSignals(False)
        table.setSortingEnabled(False)
        self.apply_filters()

        # 缓存到本地：下次双击直接用缓存
        self.lib.set_topic_chapters("kuaikan", title, chapters)
        self.lib.upsert_topic("kuaikan", title, self.current_topic.topic_url, os.path.join(self.s.save_root, title))

    def apply_filters(self):
        self.refresh_library()  # 左侧也按关键词过滤
        kw = self.search.text().strip().lower()
        for r in range(self.chapterTable.rowCount()):
            title = self.chapterTable.item(r, 3).text().lower()
            hide = bool(kw and kw not in title)
            self.chapterTable.setRowHidden(r, hide)

    def start_download_clicked(self):
        # 为安全：启动前强制关闭允许重复下载（需要用户再去设置里重开）
        if self.s.allow_redownload:
            self.s.allow_redownload = False
            self.s.save(self.settings_path)
            self.log("为了避免误操作，已自动关闭『允许重复下载』。如需重复下载，请到设置里重新勾选。")
        chapters = []
        for r in range(self.chapterTable.rowCount()):
            if self.chapterTable.isRowHidden(r): continue
            if self.chapterTable.item(r,0).checkState() == Qt.CheckState.Checked:
                ch = self.chapterTable.item(r,0).data(Qt.ItemDataRole.UserRole)
                chapters.append(ch)
        if not chapters:
            QMessageBox.information(self, "提示", "请先勾选要下载的章节。")
            return
        if not self.current_topic:
            QMessageBox.warning(self, "提示", "请先选择漫画。")
            return
        self.lock_ui(True)
        self.totalProgress.setValue(0)
        for r in range(self.chapterTable.rowCount()):
            if self.chapterTable.item(r,0).checkState() == Qt.CheckState.Checked:
                self.chapterTable.item(r,4).setText("下载中")
                self.chapterTable.item(r,6).setText("")
        self.worker = DownloadWorker(self.adapter, self.current_topic.title, chapters)
        self.worker.sigLog.connect(self.log)
        self.worker.sigChapterStarted.connect(self.on_chapter_started)
        self.worker.sigProgress.connect(self.on_progress)
        self.worker.sigChapterDone.connect(self.on_chapter_done)
        self.worker.sigChapterFailed.connect(self.on_chapter_failed)
        self.worker.sigAllDone.connect(self.on_all_done)
        self.worker.start()

    def on_chapter_started(self, ch: dict):
        for r in range(self.chapterTable.rowCount()):
            row_ch = self.chapterTable.item(r,0).data(Qt.ItemDataRole.UserRole)
            if row_ch.get("order")==ch.get("order"):
                self.chapterTable.item(r,4).setText("下载中")
                break

    def on_progress(self, chapter_idx: int, done: int, total: int):
        ch = self.worker.chapters[chapter_idx]
        for r in range(self.chapterTable.rowCount()):
            row_ch = self.chapterTable.item(r,0).data(Qt.ItemDataRole.UserRole)
            if row_ch.get("order")==ch.get("order"):
                item = self.chapterTable.item(r,5)
                item.setText(f"{done}/{total}")
                item.setData(Qt.ItemDataRole.UserRole, done)
                item.setData(Qt.ItemDataRole.UserRole+1, total)
                break
        # total progress as average across chapters
        total_ch = len(self.worker.chapters)
        accum = 0
        for i in range(total_ch):
            row = i  # approximate: treat earlier chapters finished -> 100%, current ratio else 0
        perc = int(((chapter_idx) / max(1, total_ch)) * 100)
        self.totalProgress.setValue(min(perc, 100))

    def on_chapter_done(self, chapter_idx: int):
        ch = self.worker.chapters[chapter_idx]
        for r in range(self.chapterTable.rowCount()):
            row_ch = self.chapterTable.item(r,0).data(Qt.ItemDataRole.UserRole)
            if row_ch.get("order")==ch.get("order"):
                self.chapterTable.item(r,4).setText("已完成")
                break

    def on_chapter_failed(self, chapter_idx: int, msg: str):
        ch = self.worker.chapters[chapter_idx]
        for r in range(self.chapterTable.rowCount()):
            row_ch = self.chapterTable.item(r,0).data(Qt.ItemDataRole.UserRole)
            if row_ch.get("order")==ch.get("order"):
                self.chapterTable.item(r,4).setText("失败")
                self.chapterTable.item(r,6).setText(msg)
                break

    def on_all_done(self):
        self.log("全部任务完成")
        # 自动复位
        if self.s.allow_redownload:
            self.s.allow_redownload = False
            self.s.save(self.settings_path)
            self.log("下载结束：已自动关闭『允许重复下载』。")
        self.lock_ui(False)

    def pause_clicked(self):
        if self.worker:
            self.worker.pause()
            self.btnPause.setEnabled(False)
            self.btnResume.setEnabled(True)

    def resume_clicked(self):
        if self.worker:
            self.worker.resume()
            self.btnPause.setEnabled(True)
            self.btnResume.setEnabled(False)

    def cancel_clicked(self):
        if self.worker:
            self.worker.cancel()

    def lock_ui(self, locked: bool):
        self.btnFetch.setDisabled(locked)
        self.btnStart.setDisabled(locked)
        self.btnPause.setEnabled(locked)
        self.btnResume.setEnabled(False)
        self.btnCancel.setEnabled(locked)
        self.libraryList.setDisabled(locked)
        self.search.setDisabled(locked)
        self.toggleShowAll.setDisabled(locked)

    def open_settings(self):
        dlg = SettingsDialog(self.s, self)
        if dlg.exec():
            self.s = dlg.get()
            self.s.save(self.settings_path)
            self.lib = Library(self.s.save_root, self.data_dir)
            self.refresh_library()


    def add_topic_dialog(self):
        from PyQt6.QtWidgets import QInputDialog
        title, ok = QInputDialog.getText(self, "新增漫画", "漫画标题：")
        if not ok or not title.strip():
            return
        url, ok2 = QInputDialog.getText(self, "新增漫画", "专题URL（快看）：")
        if not ok2 or not url.strip():
            return
        self.lib.upsert_topic("kuaikan", title.strip(), url.strip(), os.path.join(self.s.save_root, title.strip()))
        self.refresh_library()
        self.log(f"已新增：{title}")

    def set_topic_url_dialog(self):
        if not self.current_topic:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", "请先从左侧选择一个漫画，再设置URL。")
            return
        from PyQt6.QtWidgets import QInputDialog
        url, ok = QInputDialog.getText(self, "设置URL", "专题URL（快看）：", text=self.current_topic.topic_url or "")
        if not ok or not url.strip():
            return
        self.lib.upsert_topic("kuaikan", self.current_topic.title, url.strip(), os.path.join(self.s.save_root, self.current_topic.title))
        self.current_topic.topic_url = url.strip()
        self.log("URL 已更新")
    def select_all_rows(self):
        for r in range(self.chapterTable.rowCount()):
            if not self.chapterTable.isRowHidden(r):
                self.chapterTable.item(r, 0).setCheckState(Qt.CheckState.Checked)

    def select_none_rows(self):
        for r in range(self.chapterTable.rowCount()):
            if not self.chapterTable.isRowHidden(r):
                self.chapterTable.item(r, 0).setCheckState(Qt.CheckState.Unchecked)

    def mark_selected_as_downloaded(self):
        """把已勾选的章节标记为已下载（更新UI并写入本地缓存；配合‘仅显示未下载’自动隐藏）"""
        if not self.current_topic:
            QMessageBox.warning(self, "提示", "请先选择漫画。")
            return

        orders = []
        for r in range(self.chapterTable.rowCount()):
            if self.chapterTable.isRowHidden(r):
                continue
            if self.chapterTable.item(r, 0).checkState() == Qt.CheckState.Checked:
                # UI 更新状态
                self.chapterTable.item(r, 4).setText("已存在")
                # 记录 order 用于写缓存
                try:
                    orders.append(int(self.chapterTable.item(r, 1).text()))
                except Exception:
                    pass
                # 清勾选
                self.chapterTable.item(r, 0).setCheckState(Qt.CheckState.Unchecked)

        # 写入缓存（下次进来仍显示为已下载）
        if orders:
            self.lib.mark_chapters_downloaded("kuaikan", self.current_topic.title, orders)

        # 根据“仅显示未下载”开关进行隐藏
        self.apply_filters()

    def on_item_changed(self, item: QTableWidgetItem):
        if self._block_item_changed:
            return
        # 只关心“选”这一列
        if item.column() != 0:
            return
        row = item.row()
        status_text = self.chapterTable.item(row, 4).text()  # “状态”列
        # 如果是已下载，且设置中不允许重复下载，则不允许勾选，并提示去设置
        if status_text in ("已存在", "已完成") and not self.s.allow_redownload:
            self._block_item_changed = True
            try:
                item.setCheckState(Qt.CheckState.Unchecked)
            finally:
                self._block_item_changed = False
            QMessageBox.information(self, "提示",
                "该章节已下载。\n如需重复下载，请先在『设置』中勾选【允许重复下载（风险项）】，再操作。")
