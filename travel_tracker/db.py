"""SQLite storage for Travel Tracker.

Each employee runs the app on their own computer, so the database lives in the
user's profile folder (on Windows ``%APPDATA%\\TravelTracker\\data.db``).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    title            TEXT NOT NULL DEFAULT '',
    first_name       TEXT NOT NULL DEFAULT '',
    last_name        TEXT NOT NULL DEFAULT '',
    address          TEXT NOT NULL DEFAULT '',
    company_name     TEXT NOT NULL DEFAULT '',
    company_street   TEXT NOT NULL DEFAULT '',
    company_city     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS vehicles (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    plate                TEXT NOT NULL,
    name                 TEXT NOT NULL DEFAULT '',
    consumption_l_100km  REAL NOT NULL,
    fuel_type            TEXT NOT NULL DEFAULT 'nafta',
    is_default           INTEGER NOT NULL DEFAULT 0,
    active               INTEGER NOT NULL DEFAULT 1
);

-- Sadzby podľa zákona č. 283/2002 Z.z. (menia sa opatreniami MPSVR SR),
-- preto sú uložené s dátumom platnosti a pre cestu sa berie posledná platná.
CREATE TABLE IF NOT EXISTS domestic_rates (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    valid_from     TEXT NOT NULL UNIQUE,      -- ISO dátum YYYY-MM-DD
    km_rate        REAL NOT NULL,             -- základná náhrada €/km
    meal_5_12      REAL NOT NULL,             -- stravné 5 až 12 hodín
    meal_12_18     REAL NOT NULL,             -- stravné nad 12 až 18 hodín
    meal_over_18   REAL NOT NULL              -- stravné nad 18 hodín
);

-- Zahraničné stravné (opatrenie MF SR): sadzba za 100 % (nad 12 hodín).
CREATE TABLE IF NOT EXISTS foreign_rates (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    country        TEXT NOT NULL,
    currency       TEXT NOT NULL,
    daily_rate     REAL NOT NULL,
    valid_from     TEXT NOT NULL,
    UNIQUE (country, valid_from)
);

CREATE TABLE IF NOT EXISTS domestic_trips (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id     INTEGER NOT NULL REFERENCES vehicles(id),
    start          TEXT NOT NULL,             -- ISO dátum a čas odchodu
    end            TEXT NOT NULL,             -- ISO dátum a čas príchodu
    origin         TEXT NOT NULL,
    destination    TEXT NOT NULL,
    purpose        TEXT NOT NULL DEFAULT 'Služobne',
    km             REAL NOT NULL,
    fuel_price     REAL NOT NULL,             -- € za liter
    meal_manual    REAL                       -- ručne zadané stravné (inak automaticky)
);
CREATE INDEX IF NOT EXISTS idx_domestic_trips_start ON domestic_trips(start);

CREATE TABLE IF NOT EXISTS foreign_trips (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    country         TEXT NOT NULL,
    place           TEXT NOT NULL,             -- miesto pobytu
    purpose         TEXT NOT NULL,
    exchange_rate   REAL NOT NULL DEFAULT 1,   -- koľko jednotiek cudzej meny za 1 EUR (ECB)
    rate_date       TEXT,                      -- dátum kurzového lístka
    prepayment      TEXT NOT NULL DEFAULT 'firemná bankomatová karta',
    advance_eur     REAL NOT NULL DEFAULT 0    -- prídel valút / záloha
);

CREATE TABLE IF NOT EXISTS foreign_segments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id       INTEGER NOT NULL REFERENCES foreign_trips(id) ON DELETE CASCADE,
    seq           INTEGER NOT NULL,
    transport     TEXT NOT NULL,
    from_place    TEXT NOT NULL,
    depart_date   TEXT NOT NULL,
    depart_time   TEXT,                      -- HH:MM, môže chýbať
    to_place      TEXT NOT NULL,
    arrive_date   TEXT NOT NULL,
    arrive_time   TEXT,
    km            REAL
);

-- Ručná úprava diét pre konkrétny deň (napr. 25/50/100 %, alebo 0 pri bezplatnej strave).
CREATE TABLE IF NOT EXISTS foreign_day_overrides (
    trip_id   INTEGER NOT NULL REFERENCES foreign_trips(id) ON DELETE CASCADE,
    day       TEXT NOT NULL,
    percent   INTEGER NOT NULL,
    PRIMARY KEY (trip_id, day)
);

CREATE TABLE IF NOT EXISTS foreign_expenses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id       INTEGER NOT NULL REFERENCES foreign_trips(id) ON DELETE CASCADE,
    category      TEXT NOT NULL CHECK (category IN ('accommodation', 'other', 'paid_by_company')),
    day           TEXT NOT NULL,
    description   TEXT NOT NULL,
    amount_eur    REAL NOT NULL,
    attachment    TEXT                       -- cesta k faktúre (PDF)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Predvolené hodnoty. Sadzba 0,313 €/km a stravné 13,80 € (12–18 h) sú prevzaté
# z existujúcich podkladov; ostatné sadzby si treba overiť v platnom opatrení.
DEFAULT_DOMESTIC_RATES = {
    "valid_from": "2025-01-01",
    "km_rate": 0.313,
    "meal_5_12": 9.30,
    "meal_12_18": 13.80,
    "meal_over_18": 20.60,
}

DEFAULT_FOREIGN_RATES = [
    # krajina, mena, sadzba 100 %
    ("Švajčiarsko", "CHF", 80.0),
    ("Poľsko", "EUR", 37.0),
]


def default_db_path() -> Path:
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "TravelTracker" / "data.db"


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open (and if needed create and seed) the database."""
    if path is None:
        path = default_db_path()
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    if row is None:
        _seed(conn)
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
    conn.commit()


def _seed(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT OR IGNORE INTO profile (id) VALUES (1)")
    conn.execute(
        """INSERT OR IGNORE INTO domestic_rates
           (valid_from, km_rate, meal_5_12, meal_12_18, meal_over_18)
           VALUES (:valid_from, :km_rate, :meal_5_12, :meal_12_18, :meal_over_18)""",
        DEFAULT_DOMESTIC_RATES,
    )
    conn.executemany(
        """INSERT OR IGNORE INTO foreign_rates (country, currency, daily_rate, valid_from)
           VALUES (?, ?, ?, '2025-01-01')""",
        DEFAULT_FOREIGN_RATES,
    )
