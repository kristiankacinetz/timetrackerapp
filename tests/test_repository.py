from datetime import date

import pytest

from travel_tracker import db
from travel_tracker import repository as repo


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    yield c
    c.close()


def test_seeded_defaults(conn):
    rates = repo.list_domestic_rates(conn)
    assert len(rates) == 1
    assert rates[0].km_rate == pytest.approx(0.313)
    assert rates[0].meal_12_18 == pytest.approx(13.80)
    countries = {r.country for r in repo.list_foreign_rates(conn)}
    assert {"Švajčiarsko", "Poľsko"} <= countries


def test_reopen_does_not_reseed(tmp_path):
    path = tmp_path / "x.db"
    db.connect(path).close()
    c = db.connect(path)
    assert len(repo.list_domestic_rates(c)) == 1


def test_profile_roundtrip(conn):
    p = repo.Profile(title="Ing.", first_name="Ján", last_name="Novák", address="Hlavná 1, Žilina",
                     company_name="Firma s.r.o.", company_street="Ulica 2", company_city="010 01 Žilina")
    repo.save_profile(conn, p)
    assert repo.get_profile(conn) == p
    assert p.full_name == "Ing. Ján Novák"


def test_vehicle_default_handling(conn):
    a = repo.Vehicle(plate="ba123xx", consumption_l_100km=5.0)
    repo.save_vehicle(conn, a)
    vs = repo.list_vehicles(conn)
    assert vs[0].plate == "BA123XX"
    assert vs[0].is_default  # prvé vozidlo je automaticky predvolené

    b = repo.Vehicle(plate="ZA999AA", consumption_l_100km=4.0, is_default=True)
    repo.save_vehicle(conn, b)
    defaults = [v.plate for v in repo.list_vehicles(conn) if v.is_default]
    assert defaults == ["ZA999AA"]

    repo.deactivate_vehicle(conn, b.id)
    vs = repo.list_vehicles(conn)
    assert [v.plate for v in vs] == ["BA123XX"]
    assert len(repo.list_vehicles(conn, include_inactive=True)) == 2


def test_vehicle_validation(conn):
    with pytest.raises(ValueError):
        repo.save_vehicle(conn, repo.Vehicle(plate="", consumption_l_100km=5))
    with pytest.raises(ValueError):
        repo.save_vehicle(conn, repo.Vehicle(plate="BA1", consumption_l_100km=0))


def test_domestic_rates_by_date(conn):
    repo.save_domestic_rates(conn, repo.DomesticRates("2026-07-01", 0.35, 10, 15, 22))
    assert repo.domestic_rates_for(conn, date(2026, 6, 30)).km_rate == pytest.approx(0.313)
    assert repo.domestic_rates_for(conn, date(2026, 7, 1)).km_rate == pytest.approx(0.35)
    with pytest.raises(LookupError):
        repo.domestic_rates_for(conn, date(2020, 1, 1))


def test_cannot_delete_last_domestic_rates(conn):
    only = repo.list_domestic_rates(conn)[0]
    with pytest.raises(ValueError):
        repo.delete_domestic_rates(conn, only.id)


def test_foreign_rate_by_date(conn):
    repo.save_foreign_rate(conn, repo.ForeignRate("Švajčiarsko", "chf", 85, "2026-09-01"))
    assert repo.foreign_rate_for(conn, "Švajčiarsko", date(2026, 6, 10)).daily_rate == 80
    r = repo.foreign_rate_for(conn, "Švajčiarsko", date(2026, 10, 1))
    assert (r.daily_rate, r.currency) == (85, "CHF")
    with pytest.raises(LookupError):
        repo.foreign_rate_for(conn, "Nórsko", date(2026, 1, 1))
