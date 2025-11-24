
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionProgressBar, QStyle
from PyQt6.QtCore import Qt

class ProgressDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        value = index.data(Qt.ItemDataRole.UserRole) or 0
        total = index.data(Qt.ItemDataRole.UserRole + 1) or 0
        percent = int((value / total) * 100) if total else 0
        bar = QStyleOptionProgressBar()
        bar.rect = option.rect
        bar.minimum = 0
        bar.maximum = 100
        bar.progress = percent
        bar.text = f"{value}/{total}" if total else ""
        bar.textVisible = True
        option.widget.style().drawControl(QStyle.ControlElement.CE_ProgressBar, bar, painter)
