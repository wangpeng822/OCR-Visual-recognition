from __future__ import annotations

import sys

from app.ui.main_window import MainWindow
from app.ui.qt_compat import QApplication


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("OCR NFC Desktop")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
