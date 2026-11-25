from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QTabWidget

from .domestic import DomesticTab
from .foreign import ForeignTab
from .settings import SettingsWidget


def _placeholder(text: str) -> QLabel:
    label = QLabel(text)
    label.setAlignment(Qt.AlignCenter)
    return label


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.setWindowTitle("Travel Tracker – pracovné cesty")
        self.resize(1000, 680)
        tabs = QTabWidget()
        tabs.addTab(DomesticTab(conn), "Tuzemské cesty")
        tabs.addTab(ForeignTab(conn), "Zahraničné cesty")
        tabs.addTab(SettingsWidget(conn), "Nastavenia")
        self.setCentralWidget(tabs)
