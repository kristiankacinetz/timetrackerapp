"""Zahraničné pracovné cesty: úseky, diéty a výdavky.

Diéty sa počítajú po kalendárnych dňoch podľa času stráveného na ceste v danom
dni (od prvého odchodu po posledný príchod), ako v doterajších cestovných príkazoch:
  do 6 hodín 25 %, nad 6 do 12 hodín 50 %, nad 12 hodín 100 % dennej sadzby.
Ak čas odchodu/príchodu chýba, berie sa celý deň.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from . import repository as repo

CATEGORIES = {
    "accommodation": "Ubytovanie",
    "other": "Ostatné výdavky",
    "paid_by_company": "Hradené firmou / partnerom",
}
TRANSPORTS = ["Auto", "Lietadlo", "Vlak", "Autobus", "Taxi", "MHD", "Loď", "Iné"]


@dataclass
class Segment:
    transport: str
    from_place: str
    depart_date: date
    to_place: str
    arrive_date: date
    depart_time: time | None = None
    arrive_time: time | None = None
    km: float | None = None

    @property
    def depart(self) -> datetime:
        return datetime.combine(self.depart_date, self.depart_time or time(0, 0))

    @property
    def arrive(self) -> datetime:
        if self.arrive_time is None:
            return datetime.combine(self.arrive_date + timedelta(days=1), time(0, 0))
        return datetime.combine(self.arrive_date, self.arrive_time)


@dataclass
class Expense:
    category: str
    day: date
    description: str
    amount_eur: float
    attachment: str | None = None


@dataclass
class ForeignTrip:
    country: str
    place: str
    purpose: str
    exchange_rate: float = 1.0
    rate_date: date | None = None
    prepayment: str = "firemná bankomatová karta"
    advance_eur: float = 0.0
    segments: list[Segment] = field(default_factory=list)
    expenses: list[Expense] = field(default_factory=list)
    day_overrides: dict[date, int] = field(default_factory=dict)
    id: int | None = None

    @property
    def start(self) -> datetime | None:
        return min((s.depart for s in self.segments), default=None)

    @property
    def end(self) -> datetime | None:
        return max((s.arrive for s in self.segments), default=None)

    @property
    def date_from(self) -> date | None:
        return min((s.depart_date for s in self.segments), default=None)

    @property
    def date_to(self) -> date | None:
        return max((s.arrive_date for s in self.segments), default=None)

    @property
    def transport_summary(self) -> str:
        seen: list[str] = []
        for s in self.segments:
            if s.transport not in seen:
                seen.append(s.transport)
        return ", ".join(seen)

    def term(self) -> str:
        if not self.segments:
            return ""
        return f"{self.date_from:%d.%m.%Y} - {self.date_to:%d.%m.%Y}"


@dataclass
class AllowanceDay:
    day: date
    hours: float
    percent: int
    overridden: bool
    amount_foreign: float      # v mene sadzby
    amount_eur: float


@dataclass
class Settlement:
    currency: str
    daily_rate: float
    days: list[AllowanceDay]
    accommodation: float
    other: float
    paid_by_company: float
    advance: float

    @property
    def allowance_eur(self) -> float:
        return sum(d.amount_eur for d in self.days)

    @property
    def claims(self) -> float:
        """Nároky zamestnanca: diéty + ubytovanie + ostatné výdavky, ktoré platil sám."""
        return self.allowance_eur + self.accommodation + self.other

    @property
    def to_pay(self) -> float:
        """Kladné = dostane pracovník, záporné = vráti do pokladne."""
        return self.claims - self.advance


# ---------------------------------------------------------------- výpočet

def percent_for_hours(hours: float) -> int:
    if hours <= 0:
        return 0
    if hours <= 6:
        return 25
    if hours <= 12:
        return 50
    return 100


def to_eur(amount: float, currency: str, exchange_rate: float) -> float:
    if currency.upper() == "EUR":
        return amount
    return amount / exchange_rate


def allowance_days(trip: ForeignTrip, currency: str, daily_rate: float) -> list[AllowanceDay]:
    start, end = trip.start, trip.end
    if start is None or end is None or end <= start:
        return []
    out = []
    day = start.date()
    while datetime.combine(day, time(0)) < end:
        lo = max(start, datetime.combine(day, time(0)))
        hi = min(end, datetime.combine(day + timedelta(days=1), time(0)))
        hours = (hi - lo).total_seconds() / 3600
        overridden = day in trip.day_overrides
        pct = trip.day_overrides[day] if overridden else percent_for_hours(hours)
        amount = daily_rate * pct / 100
        out.append(AllowanceDay(day, hours, pct, overridden, amount,
                                to_eur(amount, currency, trip.exchange_rate)))
        day += timedelta(days=1)
    return out


def settle(conn: sqlite3.Connection, trip: ForeignTrip) -> Settlement:
    if trip.date_from is None:
        raise ValueError("Cesta nemá žiadne úseky.")
    rate = repo.foreign_rate_for(conn, trip.country, trip.date_from)
    days = allowance_days(trip, rate.currency, rate.daily_rate)

    def total(cat: str) -> float:
        return sum(e.amount_eur for e in trip.expenses if e.category == cat)

    return Settlement(rate.currency, rate.daily_rate, days, total("accommodation"),
                      total("other"), total("paid_by_company"), trip.advance_eur)


# ---------------------------------------------------------------- DB

def _t(s: str | None) -> time | None:
    return time.fromisoformat(s) if s else None


def _ts(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t else None


def validate(trip: ForeignTrip) -> None:
    if not trip.country.strip():
        raise ValueError("Vyberte krajinu.")
    if not trip.segments:
        raise ValueError("Pridajte aspoň jeden úsek cesty.")
    for i, s in enumerate(trip.segments, 1):
        if s.arrive <= s.depart:
            raise ValueError(f"Úsek {i}: príchod musí byť po odchode.")
    if trip.exchange_rate <= 0:
        raise ValueError("Kurz musí byť kladný.")
    for e in trip.expenses:
        if e.category not in CATEGORIES:
            raise ValueError(f"Neznáma kategória výdavku: {e.category}")


def save_trip(conn: sqlite3.Connection, trip: ForeignTrip) -> int:
    validate(trip)
    head = dict(country=trip.country.strip(), place=trip.place.strip(), purpose=trip.purpose.strip(),
                exchange_rate=trip.exchange_rate,
                rate_date=trip.rate_date.isoformat() if trip.rate_date else None,
                prepayment=trip.prepayment, advance_eur=trip.advance_eur)
    with conn:
        if trip.id is None:
            cur = conn.execute(
                """INSERT INTO foreign_trips (country, place, purpose, exchange_rate, rate_date,
                       prepayment, advance_eur)
                   VALUES (:country, :place, :purpose, :exchange_rate, :rate_date, :prepayment,
                           :advance_eur)""", head)
            trip.id = cur.lastrowid
        else:
            conn.execute(
                """UPDATE foreign_trips SET country = :country, place = :place, purpose = :purpose,
                       exchange_rate = :exchange_rate, rate_date = :rate_date,
                       prepayment = :prepayment, advance_eur = :advance_eur WHERE id = :id""",
                {**head, "id": trip.id})
            for table in ("foreign_segments", "foreign_day_overrides", "foreign_expenses"):
                conn.execute(f"DELETE FROM {table} WHERE trip_id = ?", (trip.id,))
        conn.executemany(
            """INSERT INTO foreign_segments (trip_id, seq, transport, from_place, depart_date,
                   depart_time, to_place, arrive_date, arrive_time, km)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(trip.id, i, s.transport, s.from_place, s.depart_date.isoformat(), _ts(s.depart_time),
              s.to_place, s.arrive_date.isoformat(), _ts(s.arrive_time), s.km)
             for i, s in enumerate(sorted(trip.segments, key=lambda s: s.depart))])
        conn.executemany(
            "INSERT INTO foreign_day_overrides (trip_id, day, percent) VALUES (?, ?, ?)",
            [(trip.id, d.isoformat(), p) for d, p in trip.day_overrides.items()])
        conn.executemany(
            """INSERT INTO foreign_expenses (trip_id, category, day, description, amount_eur, attachment)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(trip.id, e.category, e.day.isoformat(), e.description, e.amount_eur, e.attachment)
             for e in trip.expenses])
    return trip.id


def load_trip(conn: sqlite3.Connection, trip_id: int) -> ForeignTrip:
    row = conn.execute("SELECT * FROM foreign_trips WHERE id = ?", (trip_id,)).fetchone()
    if row is None:
        raise LookupError(f"Cesta {trip_id} neexistuje.")
    trip = ForeignTrip(
        country=row["country"], place=row["place"], purpose=row["purpose"],
        exchange_rate=row["exchange_rate"],
        rate_date=date.fromisoformat(row["rate_date"]) if row["rate_date"] else None,
        prepayment=row["prepayment"], advance_eur=row["advance_eur"], id=row["id"],
    )
    for s in conn.execute("SELECT * FROM foreign_segments WHERE trip_id = ? ORDER BY seq", (trip_id,)):
        trip.segments.append(Segment(
            s["transport"], s["from_place"], date.fromisoformat(s["depart_date"]),
            s["to_place"], date.fromisoformat(s["arrive_date"]),
            _t(s["depart_time"]), _t(s["arrive_time"]), s["km"]))
    for o in conn.execute("SELECT * FROM foreign_day_overrides WHERE trip_id = ?", (trip_id,)):
        trip.day_overrides[date.fromisoformat(o["day"])] = o["percent"]
    for e in conn.execute("SELECT * FROM foreign_expenses WHERE trip_id = ? ORDER BY id", (trip_id,)):
        trip.expenses.append(Expense(e["category"], date.fromisoformat(e["day"]), e["description"],
                                     e["amount_eur"], e["attachment"]))
    return trip


def list_trips(conn: sqlite3.Connection) -> list[ForeignTrip]:
    ids = [r["id"] for r in conn.execute("SELECT id FROM foreign_trips")]
    trips = [load_trip(conn, i) for i in ids]
    return sorted(trips, key=lambda t: t.start or datetime.min, reverse=True)


def delete_trip(conn: sqlite3.Connection, trip_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM foreign_trips WHERE id = ?", (trip_id,))
