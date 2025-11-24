
import os, sys
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow
import faulthandler
faulthandler.enable()

def main():
    base = os.path.dirname(os.path.abspath(__file__))
    qss_path = os.path.join(base, "assets", "dark.qss")
    settings_path = os.path.join(base, "data", "settings.json")
    data_dir = os.path.join(base, "data")
    os.makedirs(data_dir, exist_ok=True)

    app = QApplication(sys.argv)
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    w = MainWindow(settings_path, data_dir)
    w.resize(1200, 800)
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
