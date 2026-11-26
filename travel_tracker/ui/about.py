"""Okno Info o aplikácii."""

from __future__ import annotations

import platform
import sqlite3
from pathlib import Path

from PySide6 import __version__ as qt_version
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout

from .. import __app_name__, __author__, __version__, db


class AboutDialog(QDialog):
    def __init__(self, parent, conn: sqlite3.Connection):
        super().__init__(parent)
        self.setWindowTitle(f"O aplikácii {__app_name__}")
        self.setMinimumWidth(460)

        title = QLabel(f"<h2>{__app_name__}</h2>")
        desc = QLabel("Evidencia tuzemských a zahraničných pracovných ciest a export podkladov "
                      "pre cestovné náhrady podľa zákona č. 283/2002 Z.z.")
        desc.setWordWrap(True)

        row = conn.execute("PRAGMA database_list").fetchone()
        db_path = Path(row["file"]) if row and row["file"] else db.default_db_path()
        schema = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()

        form = QFormLayout()
        form.addRow("Verzia:", QLabel(f"<b>{__version__}</b>"))
        form.addRow("Autor:", QLabel(__author__))
        data = QLabel(str(db_path))
        data.setTextInteractionFlags(Qt.TextSelectableByMouse)
        data.setWordWrap(True)
        form.addRow("Dáta:", data)
        form.addRow("Verzia databázy:", QLabel(schema["value"] if schema else "?"))
        form.addRow("Systém:", QLabel(f"{platform.system()} {platform.release()}, "
                                      f"Python {platform.python_version()}, Qt {qt_version}"))

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("Zavrieť")
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(title)
        lay.addWidget(desc)
        lay.addLayout(form)
        lay.addWidget(buttons)
