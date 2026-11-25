"""Záloha a obnova databázy (celý súbor data.db)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from . import db

REQUIRED_TABLES = {"profile", "vehicles", "domestic_rates", "meta"}


def default_backup_name(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return f"TravelTracker-zaloha-{now:%Y-%m-%d_%H%M}.db"


def backup_to(conn: sqlite3.Connection, path: Path | str) -> Path:
    """Konzistentná kópia databázy aj počas behu aplikácie (SQLite backup API)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    target = sqlite3.connect(str(path))
    try:
        conn.backup(target)
    finally:
        target.close()
    return path


def validate_backup(path: Path | str) -> None:
    path = Path(path)
    if not path.is_file():
        raise ValueError("Súbor zálohy neexistuje.")
    try:
        src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            src.close()
    except sqlite3.DatabaseError as e:
        raise ValueError("Vybraný súbor nie je záloha Travel Tracker.") from e
    if not REQUIRED_TABLES <= tables:
        raise ValueError("Vybraný súbor nie je záloha Travel Tracker.")


def restore_from(conn: sqlite3.Connection, path: Path | str, safety_dir: Path | str | None = None) -> Path | None:
    """Nahradí aktuálne dáta zálohou. Pred tým uloží aktuálny stav ako poistku;
    vráti cestu k tejto poistnej kópii."""
    validate_backup(path)
    safety = None
    if safety_dir is not None:
        safety = backup_to(conn, Path(safety_dir) / f"pred-obnovou-{datetime.now():%Y-%m-%d_%H%M%S}.db")
    src = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    try:
        src.backup(conn)
    finally:
        src.close()
    db._init(conn)  # doplní tabuľky, ak je záloha zo staršej verzie
    return safety
