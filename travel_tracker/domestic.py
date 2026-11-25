"""Tuzemské pracovné cesty: uloženie a výpočet náhrad.

Výpočet zodpovedá doterajším Excelom:
  paušálna náhrada = km × sadzba €/km
  náhrada za PHM   = spotreba (l/100 km) × cena PHM / 100 × km
  stravné          = podľa trvania dňa (prvý odchod až posledný príchod),
                     zapisuje sa k prvej ceste dňa.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime

from . import repository as repo


@dataclass
class DomesticTrip:
    vehicle_id: int
    start: datetime
    end: datetime
    origin: str
    destination: str
    km: float
    fuel_price: float
    purpose: str = "Služobne"
    meal_manual: float | None = None
    id: int | None = None


@dataclass
class TripLine:
    """Cesta s vypočítanými náhradami (jeden riadok výkazu)."""

    trip: DomesticTrip
    meal: float
    flat: float
    fuel: float

    @property
    def total(self) -> float:
        return self.flat + self.fuel


@dataclass
class MonthSheet:
    """Podklady pre jeden mesačný výkaz jedného vozidla."""

    year: int
    month: int
    vehicle: repo.Vehicle
    km_rate: float
    lines: list[TripLine] = field(default_factory=list)

    @property
    def meal_total(self) -> float:
        return sum(l.meal for l in self.lines)

    @property
    def km_total(self) -> float:
        return sum(l.trip.km for l in self.lines)

    @property
    def flat_total(self) -> float:
        return sum(l.flat for l in self.lines)

    @property
    def fuel_total(self) -> float:
        return sum(l.fuel for l in self.lines)

    @property
    def grand_total(self) -> float:
        return self.meal_total + self.flat_total + self.fuel_total


# ---------------------------------------------------------------- stravné

def meal_for_hours(hours: float, rates: repo.DomesticRates) -> float:
    """Stravné podľa § 5 zákona č. 283/2002 Z.z."""
    if hours < 5:
        return 0.0
    if hours <= 12:
        return rates.meal_5_12
    if hours <= 18:
        return rates.meal_12_18
    return rates.meal_over_18


# ---------------------------------------------------------------- DB

def _row_to_trip(row: sqlite3.Row) -> DomesticTrip:
    names = {f.name for f in fields(DomesticTrip)}
    data = {k: row[k] for k in row.keys() if k in names}
    data["start"] = datetime.fromisoformat(data["start"])
    data["end"] = datetime.fromisoformat(data["end"])
    return DomesticTrip(**data)


def validate(trip: DomesticTrip) -> None:
    if trip.end <= trip.start:
        raise ValueError("Príchod musí byť po odchode.")
    if not trip.origin.strip() or not trip.destination.strip():
        raise ValueError("Vyplňte odkiaľ a kam.")
    if trip.km <= 0:
        raise ValueError("Počet km musí byť kladný.")
    if trip.fuel_price <= 0:
        raise ValueError("Zadajte cenu PHM.")


def save_trip(conn: sqlite3.Connection, trip: DomesticTrip) -> int:
    validate(trip)
    data = asdict(trip)
    data["start"] = trip.start.isoformat(timespec="minutes")
    data["end"] = trip.end.isoformat(timespec="minutes")
    data["origin"] = trip.origin.strip()
    data["destination"] = trip.destination.strip()
    with conn:
        if trip.id is None:
            data.pop("id")
            cur = conn.execute(
                """INSERT INTO domestic_trips
                   (vehicle_id, start, end, origin, destination, purpose, km, fuel_price, meal_manual)
                   VALUES (:vehicle_id, :start, :end, :origin, :destination, :purpose, :km,
                           :fuel_price, :meal_manual)""",
                data,
            )
            trip.id = cur.lastrowid
        else:
            conn.execute(
                """UPDATE domestic_trips SET vehicle_id = :vehicle_id, start = :start, end = :end,
                       origin = :origin, destination = :destination, purpose = :purpose, km = :km,
                       fuel_price = :fuel_price, meal_manual = :meal_manual
                   WHERE id = :id""",
                data,
            )
    return trip.id


def delete_trip(conn: sqlite3.Connection, trip_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM domestic_trips WHERE id = ?", (trip_id,))


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return first.isoformat(), nxt.isoformat()


def trips_in_month(conn: sqlite3.Connection, year: int, month: int) -> list[DomesticTrip]:
    lo, hi = _month_bounds(year, month)
    rows = conn.execute(
        "SELECT * FROM domestic_trips WHERE start >= ? AND start < ? ORDER BY start, id",
        (lo, hi),
    )
    return [_row_to_trip(r) for r in rows]


def suggest_route(conn: sqlite3.Connection, origin: str, destination: str) -> float | None:
    """Km z poslednej cesty s rovnakou trasou (alebo opačnou)."""
    row = conn.execute(
        """SELECT km FROM domestic_trips
           WHERE (origin = ? AND destination = ?) OR (origin = ? AND destination = ?)
           ORDER BY start DESC LIMIT 1""",
        (origin, destination, destination, origin),
    ).fetchone()
    return row["km"] if row else None


def last_fuel_price(conn: sqlite3.Connection) -> float | None:
    row = conn.execute("SELECT fuel_price FROM domestic_trips ORDER BY start DESC LIMIT 1").fetchone()
    return row["fuel_price"] if row else None


def known_places(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT origin AS p FROM domestic_trips UNION SELECT destination FROM domestic_trips ORDER BY p"
    )
    return [r["p"] for r in rows]


# ---------------------------------------------------------------- výpočet

def compute_lines(conn: sqlite3.Connection, trips: list[DomesticTrip]) -> list[TripLine]:
    vehicles = {v.id: v for v in repo.list_vehicles(conn, include_inactive=True)}

    # stravné za deň: od prvého odchodu po posledný príchod
    by_day: dict[date, list[DomesticTrip]] = defaultdict(list)
    for t in trips:
        by_day[t.start.date()].append(t)
    day_meal: dict[int, float] = {}
    for day, day_trips in by_day.items():
        first = min(day_trips, key=lambda t: (t.start, t.id or 0))
        hours = (max(t.end for t in day_trips) - first.start).total_seconds() / 3600
        meal = meal_for_hours(hours, repo.domestic_rates_for(conn, day))
        for t in day_trips:
            day_meal[id(t)] = meal if t is first else 0.0

    lines = []
    for t in trips:
        rates = repo.domestic_rates_for(conn, t.start.date())
        v = vehicles[t.vehicle_id]
        meal = t.meal_manual if t.meal_manual is not None else day_meal[id(t)]
        flat = t.km * rates.km_rate
        fuel = v.consumption_l_100km * t.fuel_price / 100 * t.km
        lines.append(TripLine(t, meal, flat, fuel))
    return lines


def month_sheets(conn: sqlite3.Connection, year: int, month: int) -> list[MonthSheet]:
    """Jeden výkaz na každé vozidlo použité v danom mesiaci."""
    trips = trips_in_month(conn, year, month)
    lines = compute_lines(conn, trips)
    vehicles = {v.id: v for v in repo.list_vehicles(conn, include_inactive=True)}
    sheets: dict[int, MonthSheet] = {}
    for line in lines:
        vid = line.trip.vehicle_id
        if vid not in sheets:
            rates = repo.domestic_rates_for(conn, line.trip.start.date())
            sheets[vid] = MonthSheet(year, month, vehicles[vid], rates.km_rate)
        sheets[vid].lines.append(line)
    return list(sheets.values())
