from datetime import date, time

import pytest
from openpyxl import load_workbook

from travel_tracker import db, export_foreign as exp, foreign as fx, repository as repo


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    repo.save_profile(c, repo.Profile(title="Ing.", first_name="Kristián", last_name="Kačinetz",
                                      company_name="crinitec s.r.o.", company_street="Pražská 2",
                                      company_city="010 08 Žilina"))
    yield c
    c.close()


def bern_trip() -> fx.ForeignTrip:
    """Cesta do Bernu 06/2026 podľa pôvodného cestovného príkazu."""
    d8, d11 = date(2026, 6, 8), date(2026, 6, 11)
    segs = [
        fx.Segment("Taxi", "Bratislava", d8, "Viedeň - Schwechat", d8, time(16, 0), time(17, 0)),
        fx.Segment("Lietadlo", "Viedeň - Schwechat", d8, "Bazilej", d8, time(18, 20), time(20, 0)),
        fx.Segment("Vlak", "Bazilej", d8, "Bern", d8, time(21, 0), time(22, 0)),
        fx.Segment("Vlak", "Bern", d11, "Zurich", d11, time(15, 0), time(16, 30)),
        fx.Segment("Lietadlo", "Zurich", d11, "Viedeň - Schwechat", d11, time(18, 0), time(19, 20)),
        fx.Segment("Taxi", "Viedeň - Schwechat", d11, "Bratislava", d11, time(19, 30), time(20, 30)),
    ]
    paid = [
        (d8, "Letenka Viedeň - Bazilej, Zurich - Viedeň", 420.04), (d8, "Ubytovanie", 511.77),
        (d8, "Taxi Bratislava -> Viedeň", 60), (d11, "Taxi Viedeň -> Bratislava", 60),
        (date(2026, 6, 9), "Vlak Bern - Zurich, Zurich - Bern", 128.06),
        (date(2026, 6, 9), "Lístok Zurich City", 30.43), (d8, "Vlak Bazilej - Bern", 54.39),
        (d11, "Vlak Bern - Zurich", 65.95),
    ]
    return fx.ForeignTrip(
        country="Švajčiarsko", place="Bern, Švajčiarsko",
        purpose="Pracovné stretnutie - PI Planning DSO ROS", exchange_rate=0.9221,
        rate_date=date(2026, 6, 11), segments=segs,
        expenses=[fx.Expense("paid_by_company", d, t, a) for d, t, a in paid],
    )


def wisla_trip() -> fx.ForeignTrip:
    d1, d2 = date(2026, 7, 30), date(2026, 8, 2)
    return fx.ForeignTrip(
        country="Poľsko", place="Wisła, Poľsko", purpose="Pracovné stretnutie", exchange_rate=4.3135,
        rate_date=date(2026, 7, 31),
        segments=[fx.Segment("Auto", "Žilina", d1, "Wisła, Poľsko", d1),
                  fx.Segment("Auto", "Wisła, Poľsko", d2, "Žilina", d2)],
        expenses=[
            fx.Expense("accommodation", date(2026, 7, 28),
                       "Ubytovanie v hoteli Crystal Mountain, Wisła (Poľsko)", 699.91),
            fx.Expense("other", date(2026, 8, 1),
                       "Parkovanie a miestny poplatok - Crystal Mountain, Wisła", 58.47),
        ],
    )


def test_percent_bands():
    assert fx.percent_for_hours(0) == 0
    assert fx.percent_for_hours(6) == 25
    assert fx.percent_for_hours(6.01) == 50
    assert fx.percent_for_hours(12) == 50
    assert fx.percent_for_hours(12.5) == 100


def test_bern_allowance_matches_original(conn):
    s = fx.settle(conn, bern_trip())
    assert [d.percent for d in s.days] == [50, 100, 100, 100]
    chf_to_eur = 1 / 0.9221
    expected = (40 + 80 + 80 + 80) * chf_to_eur
    assert s.allowance_eur == pytest.approx(expected)
    assert s.claims == pytest.approx(expected)  # výdavky hradila firma
    assert s.paid_by_company == pytest.approx(1330.64)


def test_wisla_without_times_counts_full_days(conn):
    s = fx.settle(conn, wisla_trip())
    assert [d.percent for d in s.days] == [100, 100, 100, 100]
    assert s.allowance_eur == pytest.approx(4 * 37)
    assert s.claims == pytest.approx(148 + 699.91 + 58.47)
    assert s.to_pay == pytest.approx(s.claims)


def test_day_override(conn):
    t = wisla_trip()
    t.day_overrides[date(2026, 7, 30)] = 50
    s = fx.settle(conn, t)
    assert s.days[0].percent == 50 and s.days[0].overridden
    assert s.allowance_eur == pytest.approx(18.5 + 3 * 37)


def test_save_and_load_roundtrip(conn):
    t = bern_trip()
    t.day_overrides[date(2026, 6, 9)] = 25
    fx.save_trip(conn, t)
    loaded = fx.load_trip(conn, t.id)
    assert loaded == t
    assert loaded.transport_summary == "Taxi, Lietadlo, Vlak"
    assert loaded.term() == "08.06.2026 - 11.06.2026"
    # úprava nahradí úseky/výdavky, nie pridá
    loaded.segments = loaded.segments[:2]
    fx.save_trip(conn, loaded)
    assert len(fx.load_trip(conn, t.id).segments) == 2
    assert [x.id for x in fx.list_trips(conn)] == [t.id]
    fx.delete_trip(conn, t.id)
    assert fx.list_trips(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM foreign_segments").fetchone()[0] == 0


def test_validation(conn):
    t = bern_trip()
    t.segments = []
    with pytest.raises(ValueError):
        fx.save_trip(conn, t)
    t = bern_trip()
    t.segments[0].arrive_time = time(15, 0)
    with pytest.raises(ValueError):
        fx.save_trip(conn, t)


def test_unknown_country_rate(conn):
    t = bern_trip()
    t.country = "Nórsko"
    with pytest.raises(LookupError):
        fx.settle(conn, t)


def test_export_bern(conn, tmp_path):
    t = bern_trip()
    s = fx.settle(conn, t)
    path = exp.export_trip(tmp_path / exp.default_filename(t), t, s, repo.get_profile(conn))
    assert path.name == "Zahraničná pracovná cesta - 06_2026_Bern.xlsx"
    wb = load_workbook(path)
    assert wb.sheetnames == ["Sheet1", "Sheet2", "Sheet3"]
    s1, s2, s3 = wb["Sheet1"], wb["Sheet2"], wb["Sheet3"]
    assert s1["H9"].value == "Ing. Kačinetz Kristián"
    assert s1["C12"].value == "08.06.2026 - 11.06.2026"
    assert s1["C13"].value == "Taxi, Lietadlo, Vlak"
    assert s1["A27"].value == "Taxi" and s1["H28"].value == "Bazilej"
    assert s1["G35"].value == "=Sheet3!D7"  # 50 %
    assert s1["G36"].value == "=Sheet3!D8"  # 100 %
    assert s1["G39"].value == "=SUM(G35:G38)"
    assert s3["B2"].value == 0.9221 and s3["B8"].value == 80
    totals = [r for r in s2.iter_rows() if r[0].value == "Nároky celkom:"]
    assert totals and totals[0][4].value.startswith("=Sheet1!G39+")


def test_export_wisla_eur_country(conn, tmp_path):
    t = wisla_trip()
    path = exp.export_trip(tmp_path / "w.xlsx", t, fx.settle(conn, t), repo.get_profile(conn))
    s3 = load_workbook(path)["Sheet3"]
    assert s3["D8"].value == "=B8"
    assert s3["B8"].value == 37
