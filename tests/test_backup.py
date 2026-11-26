from datetime import datetime

import pytest

from travel_tracker import backup, db, domestic as dom, repository as repo


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "data.db")
    v = repo.Vehicle(plate="BT598FY", consumption_l_100km=4)
    repo.save_vehicle(c, v)
    dom.save_trip(c, dom.DomesticTrip(v.id, datetime(2026, 2, 4, 7), datetime(2026, 2, 4, 9),
                                      "Žilina", "Bratislava", 200, 1.466))
    yield c
    c.close()


def test_backup_and_restore(conn, tmp_path):
    path = backup.backup_to(conn, tmp_path / "zaloha" / backup.default_backup_name())
    assert path.exists()

    # zmena po zálohe
    dom.delete_trip(conn, dom.trips_in_month(conn, 2026, 2)[0].id)
    assert dom.trips_in_month(conn, 2026, 2) == []

    safety = backup.restore_from(conn, path, tmp_path)
    assert len(dom.trips_in_month(conn, 2026, 2)) == 1
    assert repo.list_vehicles(conn)[0].plate == "BT598FY"

    # poistná kópia obsahuje stav pred obnovou (bez cesty)
    c2 = db.connect(safety)
    assert dom.trips_in_month(c2, 2026, 2) == []
    c2.close()


def test_backup_overwrites_existing_file(conn, tmp_path):
    path = tmp_path / "z.db"
    path.write_bytes(b"old")
    backup.backup_to(conn, path)
    backup.validate_backup(path)


def test_restore_rejects_foreign_file(conn, tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_text("not a database")
    with pytest.raises(ValueError):
        backup.restore_from(conn, bad)
    with pytest.raises(ValueError):
        backup.restore_from(conn, tmp_path / "missing.db")
    # dáta zostali nedotknuté
    assert len(dom.trips_in_month(conn, 2026, 2)) == 1


def test_default_name():
    assert backup.default_backup_name(datetime(2026, 11, 25, 18, 5)) == "TravelTracker-zaloha-2026-11-25_1805.db"


def test_version():
    import travel_tracker
    assert travel_tracker.__version__ == "6.0.0"
