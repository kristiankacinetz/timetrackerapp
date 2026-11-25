from datetime import datetime

import pytest
from openpyxl import load_workbook

from travel_tracker import db, domestic as dom, export_domestic as exp, repository as repo

# Február 2026 z pôvodného zošita "Tuzemské cesťáky hromadné 2026.xlsx"
FEB_2026 = [
    # deň, odchod, príchod, odkiaľ, kam, km, PHM
    (4, "07:00", "09:00", "Žilina", "Bratislava", 200, 1.466),
    (4, "17:30", "19:30", "Bratislava", "Žilina", 200, 1.466),
    (11, "07:00", "09:00", "Žilina", "Bratislava", 200, 1.467),
    (11, "12:00", "13:00", "Bratislava", "Chorvátsky Grob", 33, 1.467),
    (11, "15:00", "16:00", "Chorvátsky Grob", "Bratislava", 33, 1.467),
    (11, "17:30", "19:30", "Bratislava", "Žilina", 200, 1.467),
    (18, "07:00", "09:00", "Žilina", "Bratislava", 200, 1.467),
    (18, "12:00", "13:00", "Bratislava", "Chorvátsky Grob", 33, 1.467),
    (18, "15:00", "16:00", "Chorvátsky Grob", "Bratislava", 33, 1.467),
    (18, "17:30", "19:30", "Bratislava", "Žilina", 200, 1.467),
    (25, "07:00", "09:00", "Žilina", "Bratislava", 200, 1.466),
    (25, "17:30", "19:30", "Bratislava", "Žilina", 200, 1.466),
    (26, "07:00", "09:00", "Žilina", "Bratislava", 200, 1.466),
    (26, "17:30", "19:30", "Bratislava", "Žilina", 200, 1.466),
    (27, "07:00", "09:00", "Žilina", "Bratislava", 200, 1.466),
    (27, "17:30", "19:30", "Bratislava", "Žilina", 200, 1.466),
]


def _dt(day, hm):
    h, m = map(int, hm.split(":"))
    return datetime(2026, 2, day, h, m)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    repo.save_profile(c, repo.Profile(first_name="Kristián", last_name="Kačinetz",
                                      address="Pražská 2, 010 08 Žilina"))
    v = repo.Vehicle(plate="BT598FY", name="Volkswagen Passat Variant", consumption_l_100km=4)
    repo.save_vehicle(c, v)
    yield c
    c.close()


def _load_feb(conn):
    vid = repo.list_vehicles(conn)[0].id
    for day, s, e, o, d, km, fuel in FEB_2026:
        dom.save_trip(conn, dom.DomesticTrip(vid, _dt(day, s), _dt(day, e), o, d, km, fuel))
    return vid


def expected_feb():
    flat = sum(r[5] * 0.313 for r in FEB_2026)
    fuel = sum(4 * r[6] / 100 * r[5] for r in FEB_2026)
    meal = 6 * 13.80  # 6 dní, každý 7:00–19:30 = 12,5 h
    return meal, flat, fuel


def test_meal_bands():
    r = repo.DomesticRates("2025-01-01", 0.313, 9.3, 13.8, 20.6)
    assert dom.meal_for_hours(4.99, r) == 0
    assert dom.meal_for_hours(5, r) == 9.3
    assert dom.meal_for_hours(12, r) == 9.3
    assert dom.meal_for_hours(12.5, r) == 13.8
    assert dom.meal_for_hours(18, r) == 13.8
    assert dom.meal_for_hours(18.01, r) == 20.6


def test_february_matches_original(conn):
    _load_feb(conn)
    [sheet] = dom.month_sheets(conn, 2026, 2)
    meal, flat, fuel = expected_feb()
    assert len(sheet.lines) == 16
    assert sheet.meal_total == pytest.approx(meal)
    assert sheet.flat_total == pytest.approx(flat)
    assert sheet.fuel_total == pytest.approx(fuel)
    # stravné len pri prvej ceste dňa, ako v pôvodnom výkaze
    assert [l.meal for l in sheet.lines[:6]] == [13.8, 0, 13.8, 0, 0, 0]


def test_manual_meal_override(conn):
    vid = _load_feb(conn)
    first = dom.trips_in_month(conn, 2026, 2)[0]
    first.meal_manual = 5.0
    dom.save_trip(conn, first)
    [sheet] = dom.month_sheets(conn, 2026, 2)
    assert sheet.lines[0].meal == 5.0


def test_validation(conn):
    vid = repo.list_vehicles(conn)[0].id
    with pytest.raises(ValueError):
        dom.save_trip(conn, dom.DomesticTrip(vid, _dt(1, "10:00"), _dt(1, "09:00"), "A", "B", 10, 1.5))
    with pytest.raises(ValueError):
        dom.save_trip(conn, dom.DomesticTrip(vid, _dt(1, "08:00"), _dt(1, "09:00"), "A", "B", 0, 1.5))


def test_suggestions(conn):
    _load_feb(conn)
    assert dom.suggest_route(conn, "Žilina", "Bratislava") == 200
    assert dom.suggest_route(conn, "Chorvátsky Grob", "Bratislava") == 33
    assert dom.suggest_route(conn, "Košice", "Bratislava") is None
    assert dom.last_fuel_price(conn) == 1.466
    assert "Chorvátsky Grob" in dom.known_places(conn)


def test_month_boundaries(conn):
    vid = _load_feb(conn)
    dom.save_trip(conn, dom.DomesticTrip(vid, datetime(2026, 3, 1, 0, 0), datetime(2026, 3, 1, 1, 0),
                                         "A", "B", 10, 1.5))
    assert len(dom.trips_in_month(conn, 2026, 2)) == 16
    assert len(dom.trips_in_month(conn, 2026, 3)) == 1
    assert dom.trips_in_month(conn, 2026, 12) == []


def test_export_month_file(conn, tmp_path):
    _load_feb(conn)
    sheets = dom.month_sheets(conn, 2026, 2)
    out = exp.export_month_file(tmp_path / "feb.xlsx", sheets, repo.get_profile(conn))
    ws = load_workbook(out)["Február 2026"]
    assert ws["A1"].value == "Kristián Kačinetz - Cestovné príkazy 02/2026"
    assert ws["A2"].value == "ŠPZ: BT598FY"
    assert ws["D3"].value == pytest.approx(0.313)
    assert ws["H3"].value == 4
    assert ws["E7"].value == "Žilina" and ws["G7"].value == "Bratislava"
    assert ws["J7"].value == 13.8 and ws["J8"].value == 0
    assert ws["M7"].value == "=K7*$D$3"
    assert ws["N7"].value == "=($H$3*L7/$Q$4)*K7"
    assert ws["I23"].value == "Súčet"
    assert ws["O23"].value == "=SUM(O7:O22)"
    assert ws["K24"].value == "=J23+O23"


def test_export_year_workbook_adds_and_replaces(conn, tmp_path):
    vid = _load_feb(conn)
    dom.save_trip(conn, dom.DomesticTrip(vid, datetime(2026, 1, 7, 7), datetime(2026, 1, 7, 9),
                                         "Žilina", "Bratislava", 200, 1.388))
    path = tmp_path / exp.default_filename(2026)
    prof = repo.get_profile(conn)
    exp.export_into_year_workbook(path, dom.month_sheets(conn, 2026, 2), prof)
    exp.export_into_year_workbook(path, dom.month_sheets(conn, 2026, 1), prof)
    exp.export_into_year_workbook(path, dom.month_sheets(conn, 2026, 2), prof)  # nahradí
    wb = load_workbook(path)
    assert wb.sheetnames == ["Január 2026", "Február 2026"]


def test_two_vehicles_get_separate_sheets(conn, tmp_path):
    _load_feb(conn)
    v2 = repo.Vehicle(plate="ZA111AA", name="Škoda Octavia", consumption_l_100km=5.5)
    repo.save_vehicle(conn, v2)
    dom.save_trip(conn, dom.DomesticTrip(v2.id, datetime(2026, 2, 5, 8), datetime(2026, 2, 5, 9),
                                         "Žilina", "Martin", 30, 1.5))
    sheets = dom.month_sheets(conn, 2026, 2)
    assert len(sheets) == 2
    out = exp.export_month_file(tmp_path / "f.xlsx", sheets, repo.get_profile(conn))
    assert load_workbook(out).sheetnames == ["Február 2026 BT598FY", "Február 2026 ZA111AA"]
