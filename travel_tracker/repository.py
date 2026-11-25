"""Data access helpers on top of the SQLite connection."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, fields
from datetime import date


@dataclass
class Profile:
    title: str = ""
    first_name: str = ""
    last_name: str = ""
    address: str = ""
    company_name: str = ""
    company_street: str = ""
    company_city: str = ""

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.title, self.first_name, self.last_name) if p)


@dataclass
class Vehicle:
    plate: str
    consumption_l_100km: float
    name: str = ""
    fuel_type: str = "nafta"
    is_default: bool = False
    active: bool = True
    id: int | None = None


@dataclass
class DomesticRates:
    valid_from: str
    km_rate: float
    meal_5_12: float
    meal_12_18: float
    meal_over_18: float
    id: int | None = None


@dataclass
class ForeignRate:
    country: str
    currency: str
    daily_rate: float
    valid_from: str
    id: int | None = None


def _from_row(cls, row: sqlite3.Row):
    names = {f.name for f in fields(cls)}
    return cls(**{k: row[k] for k in row.keys() if k in names})


# ---------------------------------------------------------------- profil

def get_profile(conn: sqlite3.Connection) -> Profile:
    row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    return _from_row(Profile, row)


def save_profile(conn: sqlite3.Connection, profile: Profile) -> None:
    data = asdict(profile)
    cols = ", ".join(f"{k} = :{k}" for k in data)
    conn.execute(f"UPDATE profile SET {cols} WHERE id = 1", data)
    conn.commit()


# ---------------------------------------------------------------- vozidlá

def list_vehicles(conn: sqlite3.Connection, include_inactive: bool = False) -> list[Vehicle]:
    sql = "SELECT * FROM vehicles"
    if not include_inactive:
        sql += " WHERE active = 1"
    sql += " ORDER BY is_default DESC, plate"
    out = []
    for row in conn.execute(sql):
        v = _from_row(Vehicle, row)
        v.is_default, v.active = bool(v.is_default), bool(v.active)
        out.append(v)
    return out


def save_vehicle(conn: sqlite3.Connection, v: Vehicle) -> int:
    if v.consumption_l_100km <= 0:
        raise ValueError("Spotreba musí byť kladné číslo.")
    if not v.plate.strip():
        raise ValueError("ŠPZ je povinná.")
    data = asdict(v)
    data["plate"] = v.plate.strip().upper()
    with conn:
        if v.is_default:
            conn.execute("UPDATE vehicles SET is_default = 0")
        if v.id is None:
            data.pop("id")
            cur = conn.execute(
                """INSERT INTO vehicles (plate, name, consumption_l_100km, fuel_type, is_default, active)
                   VALUES (:plate, :name, :consumption_l_100km, :fuel_type, :is_default, :active)""",
                data,
            )
            v.id = cur.lastrowid
        else:
            conn.execute(
                """UPDATE vehicles SET plate = :plate, name = :name,
                       consumption_l_100km = :consumption_l_100km, fuel_type = :fuel_type,
                       is_default = :is_default, active = :active
                   WHERE id = :id""",
                data,
            )
        # Ak nie je žiadne predvolené, prvé aktívne sa stane predvoleným.
        has_default = conn.execute(
            "SELECT 1 FROM vehicles WHERE is_default = 1 AND active = 1"
        ).fetchone()
        if not has_default:
            conn.execute(
                "UPDATE vehicles SET is_default = 1 WHERE id = "
                "(SELECT id FROM vehicles WHERE active = 1 ORDER BY id LIMIT 1)"
            )
    return v.id


def deactivate_vehicle(conn: sqlite3.Connection, vehicle_id: int) -> None:
    """Vozidlo sa nemaže, aby staré cesty mali stále svoje údaje."""
    with conn:
        conn.execute(
            "UPDATE vehicles SET active = 0, is_default = 0 WHERE id = ?", (vehicle_id,)
        )


# ---------------------------------------------------------------- tuzemské sadzby

def list_domestic_rates(conn: sqlite3.Connection) -> list[DomesticRates]:
    rows = conn.execute("SELECT * FROM domestic_rates ORDER BY valid_from DESC")
    return [_from_row(DomesticRates, r) for r in rows]


def save_domestic_rates(conn: sqlite3.Connection, r: DomesticRates) -> int:
    date.fromisoformat(r.valid_from)  # validácia formátu
    data = asdict(r)
    with conn:
        if r.id is None:
            data.pop("id")
            cur = conn.execute(
                """INSERT INTO domestic_rates (valid_from, km_rate, meal_5_12, meal_12_18, meal_over_18)
                   VALUES (:valid_from, :km_rate, :meal_5_12, :meal_12_18, :meal_over_18)""",
                data,
            )
            r.id = cur.lastrowid
        else:
            conn.execute(
                """UPDATE domestic_rates SET valid_from = :valid_from, km_rate = :km_rate,
                       meal_5_12 = :meal_5_12, meal_12_18 = :meal_12_18, meal_over_18 = :meal_over_18
                   WHERE id = :id""",
                data,
            )
    return r.id


def delete_domestic_rates(conn: sqlite3.Connection, rates_id: int) -> None:
    with conn:
        count = conn.execute("SELECT COUNT(*) FROM domestic_rates").fetchone()[0]
        if count <= 1:
            raise ValueError("Musí zostať aspoň jedna sada sadzieb.")
        conn.execute("DELETE FROM domestic_rates WHERE id = ?", (rates_id,))


def domestic_rates_for(conn: sqlite3.Connection, day: date) -> DomesticRates:
    row = conn.execute(
        "SELECT * FROM domestic_rates WHERE valid_from <= ? ORDER BY valid_from DESC LIMIT 1",
        (day.isoformat(),),
    ).fetchone()
    if row is None:
        raise LookupError(f"Pre dátum {day:%d.%m.%Y} nie sú zadané tuzemské sadzby.")
    return _from_row(DomesticRates, row)


# ---------------------------------------------------------------- zahraničné sadzby

def list_foreign_rates(conn: sqlite3.Connection) -> list[ForeignRate]:
    rows = conn.execute("SELECT * FROM foreign_rates ORDER BY country, valid_from DESC")
    return [_from_row(ForeignRate, r) for r in rows]


def save_foreign_rate(conn: sqlite3.Connection, r: ForeignRate) -> int:
    date.fromisoformat(r.valid_from)
    if not r.country.strip() or not r.currency.strip():
        raise ValueError("Krajina a mena sú povinné.")
    data = asdict(r)
    data["currency"] = r.currency.strip().upper()
    with conn:
        if r.id is None:
            data.pop("id")
            cur = conn.execute(
                """INSERT INTO foreign_rates (country, currency, daily_rate, valid_from)
                   VALUES (:country, :currency, :daily_rate, :valid_from)""",
                data,
            )
            r.id = cur.lastrowid
        else:
            conn.execute(
                """UPDATE foreign_rates SET country = :country, currency = :currency,
                       daily_rate = :daily_rate, valid_from = :valid_from WHERE id = :id""",
                data,
            )
    return r.id


def delete_foreign_rate(conn: sqlite3.Connection, rate_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM foreign_rates WHERE id = ?", (rate_id,))


def foreign_rate_for(conn: sqlite3.Connection, country: str, day: date) -> ForeignRate:
    row = conn.execute(
        """SELECT * FROM foreign_rates WHERE country = ? AND valid_from <= ?
           ORDER BY valid_from DESC LIMIT 1""",
        (country, day.isoformat()),
    ).fetchone()
    if row is None:
        raise LookupError(f"Pre krajinu {country} nie je zadaná sadzba stravného.")
    return _from_row(ForeignRate, row)
