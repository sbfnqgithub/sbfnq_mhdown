
from PyQt6.QtWidgets import QDialog, QFormLayout, QLineEdit, QCheckBox, QSpinBox, QPushButton, QHBoxLayout, QFileDialog
from PyQt6.QtCore import Qt
from core.settings import AppSettings

class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setModal(True)
        self.s = settings
        lay = QFormLayout(self)

        self.save_root = QLineEdit(self.s.save_root)
        self.max_workers = QSpinBox(); self.max_workers.setRange(1, 64); self.max_workers.setValue(self.s.max_workers)
        self.jpg_quality = QSpinBox(); self.jpg_quality.setRange(10, 100); self.jpg_quality.setValue(self.s.jpg_quality)
        self.timeout = QSpinBox(); self.timeout.setRange(5, 120); self.timeout.setValue(self.s.timeout)
        self.retries = QSpinBox(); self.retries.setRange(0, 10); self.retries.setValue(self.s.retries)
        self.headless = QCheckBox("无头模式"); self.headless.setChecked(self.s.headless)
        self.chrome = QLineEdit(self.s.chrome_path); btnChrome = QPushButton("…")
        self.driver = QLineEdit(self.s.chromedriver_path); btnDriver = QPushButton("…")
        self.cookie = QLineEdit(self.s.cookie_path); btnCookie = QPushButton("…")
        self.show_downloaded = QCheckBox("显示已下载（默认关闭）"); self.show_downloaded.setChecked(self.s.show_downloaded)
        self.allow_redownload = QCheckBox("允许重复下载（风险项，默认关闭）")
        self.allow_redownload.setChecked(self.s.allow_redownload)

        lay.addRow("保存目录", self.save_root)
        lay.addRow("最大并发", self.max_workers)
        lay.addRow("JPEG质量", self.jpg_quality)
        lay.addRow("超时(秒)", self.timeout)
        lay.addRow("重试次数", self.retries)
        lay.addRow(self.headless)

        row1 = QHBoxLayout(); row1.addWidget(self.chrome); row1.addWidget(btnChrome)
        row2 = QHBoxLayout(); row2.addWidget(self.driver); row2.addWidget(btnDriver)
        row3 = QHBoxLayout(); row3.addWidget(self.cookie); row3.addWidget(btnCookie)
        lay.addRow("Chrome路径", row1)
        lay.addRow("Driver路径", row2)
        lay.addRow("Cookie文件", row3)
        lay.addRow(self.show_downloaded)
        lay.addRow(self.allow_redownload)

        btns = QHBoxLayout()
        ok = QPushButton("确定"); cancel = QPushButton("取消")
        btns.addWidget(ok); btns.addWidget(cancel)
        lay.addRow(btns)

        def pick(line: QLineEdit, files=True):
            if files:
                p,_ = QFileDialog.getOpenFileName(self, "选择文件", "", "All (*.*)")
            else:
                p = QFileDialog.getExistingDirectory(self, "选择目录", "")
            if p: line.setText(p)

        btnChrome.clicked.connect(lambda: pick(self.chrome, True))
        btnDriver.clicked.connect(lambda: pick(self.driver, True))
        btnCookie.clicked.connect(lambda: pick(self.cookie, True))
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)

    def get(self) -> AppSettings:
        s = self.s
        s.save_root = self.save_root.text().strip()
        s.max_workers = self.max_workers.value()
        s.jpg_quality = self.jpg_quality.value()
        s.timeout = self.timeout.value()
        s.retries = self.retries.value()
        s.headless = self.headless.isChecked()
        s.chrome_path = self.chrome.text().strip()
        s.chromedriver_path = self.driver.text().strip()
        s.cookie_path = self.cookie.text().strip()
        s.show_downloaded = self.show_downloaded.isChecked()
        s.allow_redownload = self.allow_redownload.isChecked()

        return s
