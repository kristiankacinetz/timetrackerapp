from __future__ import annotations

import sqlite3

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMainWindow, QTabWidget

from .domestic import DomesticTab
from .foreign import ForeignTab
from .settings import SettingsWidget


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.conn = conn
        self.setWindowTitle("Travel Tracker – pracovné cesty")
        self.resize(1000, 680)
        self._build()

    def _build(self, current: int = 0) -> None:
        tabs = QTabWidget()
        tabs.addTab(DomesticTab(self.conn), "Tuzemské cesty")
        tabs.addTab(ForeignTab(self.conn), "Zahraničné cesty")
        tabs.addTab(SettingsWidget(self.conn, on_restored=self._after_restore), "Nastavenia")
        tabs.setCurrentIndex(current)
        self.setCentralWidget(tabs)

    def _after_restore(self) -> None:
        # po obnove zálohy znovu načítať všetky záložky (mimo obsluhy tlačidla)
        QTimer.singleShot(0, lambda: self._build(current=2))
