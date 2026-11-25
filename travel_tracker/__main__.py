import sys

from PySide6.QtWidgets import QApplication

from . import db
from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Travel Tracker")
    conn = db.connect()
    window = MainWindow(conn)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
