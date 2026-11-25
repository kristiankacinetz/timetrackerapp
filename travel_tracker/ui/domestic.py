"""Záložka Tuzemské cesty: mesačný prehľad, zápis ciest a export."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QDateTime, Qt, QTime
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import domestic as dom
from .. import export_domestic as exp
from .. import repository as repo
from .settings import MONTH_NAMES, _item, _money_spin, _num, _table


def _qdt(d: datetime) -> QDateTime:
    return QDateTime(QDate(d.year, d.month, d.day), QTime(d.hour, d.minute))


def _pydt(q: QDateTime) -> datetime:
    d, t = q.date(), q.time()
    return datetime(d.year(), d.month(), d.day(), t.hour(), t.minute())


class TripDialog(QDialog):
    def __init__(self, parent, conn: sqlite3.Connection, trip: dom.DomesticTrip):
        super().__init__(parent)
        self.conn = conn
        self.trip = trip
        self.setWindowTitle("Tuzemská cesta")
        self.setMinimumWidth(420)

        self.vehicle = QComboBox()
        for v in repo.list_vehicles(conn, include_inactive=True):
            if v.active or v.id == trip.vehicle_id:
                self.vehicle.addItem(f"{v.plate} – {v.name}", v.id)
        idx = self.vehicle.findData(trip.vehicle_id)
        self.vehicle.setCurrentIndex(max(idx, 0))

        self.start = QDateTimeEdit(_qdt(trip.start))
        self.end = QDateTimeEdit(_qdt(trip.end))
        for e in (self.start, self.end):
            e.setCalendarPopup(True)
            e.setDisplayFormat("dd.MM.yyyy  HH:mm")
        self.start.dateTimeChanged.connect(self._start_changed)

        places = dom.known_places(conn)
        self.origin = QLineEdit(trip.origin)
        self.destination = QLineEdit(trip.destination)
        for e in (self.origin, self.destination):
            c = QCompleter(places, e)
            c.setCaseSensitivity(Qt.CaseInsensitive)
            e.setCompleter(c)
            e.editingFinished.connect(self._suggest_km)
        self.purpose = QLineEdit(trip.purpose)

        self.km = _money_spin(1, 5000)
        self.km.setSuffix(" km")
        self.km.setValue(trip.km)
        self.fuel = _money_spin(3, 10)
        self.fuel.setSuffix(" €/l")
        self.fuel.setValue(trip.fuel_price)

        self.meal_manual = QCheckBox("Zadať stravné ručne")
        self.meal = _money_spin()
        self.meal.setSuffix(" €")
        self.meal_manual.setChecked(trip.meal_manual is not None)
        self.meal.setValue(trip.meal_manual or 0)
        self.meal.setEnabled(self.meal_manual.isChecked())
        self.meal_manual.toggled.connect(self.meal.setEnabled)
        meal_hint = QLabel("Inak sa stravné vypočíta automaticky podľa trvania dňa\n"
                           "a zapíše sa k prvej ceste dňa.")
        meal_hint.setStyleSheet("color: gray")

        form = QFormLayout()
        form.addRow("Vozidlo:", self.vehicle)
        form.addRow("Odchod:", self.start)
        form.addRow("Príchod:", self.end)
        form.addRow("Odkiaľ:", self.origin)
        form.addRow("Kam:", self.destination)
        form.addRow("Dôvod:", self.purpose)
        form.addRow("Počet km:", self.km)
        form.addRow("Cena PHM:", self.fuel)
        form.addRow(self.meal_manual, self.meal)
        form.addRow(meal_hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _start_changed(self, new: QDateTime) -> None:
        # posun príchodu spolu s odchodom, aby zostala rovnaká dĺžka
        if self.end.dateTime() <= new:
            self.end.setDateTime(new.addSecs(3600))

    def _suggest_km(self) -> None:
        if self.km.value() == 0 and self.origin.text() and self.destination.text():
            km = dom.suggest_route(self.conn, self.origin.text().strip(), self.destination.text().strip())
            if km:
                self.km.setValue(km)

    def result_trip(self) -> dom.DomesticTrip:
        t = self.trip
        t.vehicle_id = self.vehicle.currentData()
        t.start = _pydt(self.start.dateTime())
        t.end = _pydt(self.end.dateTime())
        t.origin = self.origin.text()
        t.destination = self.destination.text()
        t.purpose = self.purpose.text().strip() or "Služobne"
        t.km = self.km.value()
        t.fuel_price = self.fuel.value()
        t.meal_manual = self.meal.value() if self.meal_manual.isChecked() else None
        return t

    def _accept(self) -> None:
        if self.vehicle.currentData() is None:
            QMessageBox.warning(self, "Cesta", "Najprv pridajte vozidlo v Nastaveniach.")
            return
        try:
            dom.save_trip(self.conn, self.result_trip())
        except ValueError as e:
            QMessageBox.warning(self, "Cesta", str(e))
            return
        self.accept()


class ExportDialog(QDialog):
    def __init__(self, parent, year: int, month: int):
        super().__init__(parent)
        self.setWindowTitle("Export do Excelu")
        self.year_mode = QRadioButton(f"Pridať do ročného zošita {year} (hárok za mesiac)")
        self.month_mode = QRadioButton(f"Samostatný súbor za {MONTH_NAMES[month - 1].lower()} {year}")
        self.year_mode.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.year_mode)
        group.addButton(self.month_mode)
        hint = QLabel("Ak ročný zošit už existuje, hárok mesiaca sa doň pridá alebo sa nahradí.")
        hint.setStyleSheet("color: gray")
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.year_mode)
        lay.addWidget(hint)
        lay.addWidget(self.month_mode)
        lay.addWidget(buttons)


class DomesticTab(QWidget):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.conn = conn
        today = date.today()

        self.month = QComboBox()
        self.month.addItems(MONTH_NAMES)
        self.month.setCurrentIndex(today.month - 1)
        self.year = QSpinBox()
        self.year.setRange(2000, 2100)
        self.year.setValue(today.year)
        prev_btn, next_btn = QPushButton("◀"), QPushButton("▶")
        prev_btn.setFixedWidth(32)
        next_btn.setFixedWidth(32)
        prev_btn.clicked.connect(lambda: self._shift(-1))
        next_btn.clicked.connect(lambda: self._shift(1))
        self.month.currentIndexChanged.connect(self.load)
        self.year.valueChanged.connect(self.load)

        top = QHBoxLayout()
        top.addWidget(QLabel("Mesiac:"))
        top.addWidget(prev_btn)
        top.addWidget(self.month)
        top.addWidget(self.year)
        top.addWidget(next_btn)
        top.addStretch()
        export_btn = QPushButton("Export do Excelu…")
        export_btn.clicked.connect(self.export)
        top.addWidget(export_btn)

        self.table = _table(["Odchod", "Príchod", "Odkiaľ", "Kam", "Dôvod", "ŠPZ",
                             "Km", "PHM €/l", "Stravné", "Paušál", "PHM", "Spolu"])
        self.table.doubleClicked.connect(self.edit)
        header = self.table.horizontalHeader()
        for col in (0, 1):
            header.setSectionResizeMode(col, header.ResizeMode.ResizeToContents)

        buttons = QHBoxLayout()
        for label, fn, tip in (
            ("Pridať", self.add, ""),
            ("Upraviť", self.edit, ""),
            ("Spiatočná", self.add_return, "Pridá cestu späť (opačná trasa, rovnaké km)"),
            ("Kopírovať", self.copy, "Pridá rovnakú cestu s novým dátumom"),
            ("Zmazať", self.delete, ""),
        ):
            b = QPushButton(label)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            buttons.addWidget(b)
        buttons.addStretch()
        self.summary = QLabel()
        self.summary.setStyleSheet("font-weight: bold")
        buttons.addWidget(self.summary)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)
        lay.addLayout(buttons)
        self.load()

    # ------------------------------------------------------------ navigácia

    def _ym(self) -> tuple[int, int]:
        return self.year.value(), self.month.currentIndex() + 1

    def _shift(self, delta: int) -> None:
        y, m = self._ym()
        m += delta
        if m < 1:
            y, m = y - 1, 12
        elif m > 12:
            y, m = y + 1, 1
        self.year.blockSignals(True)
        self.year.setValue(y)
        self.year.blockSignals(False)
        self.month.setCurrentIndex(m - 1)
        self.load()

    def showEvent(self, event) -> None:  # obnov po zmene nastavení
        super().showEvent(event)
        self.load()

    def load(self) -> None:
        y, m = self._ym()
        trips = dom.trips_in_month(self.conn, y, m)
        try:
            lines = dom.compute_lines(self.conn, trips)
        except LookupError as e:
            QMessageBox.warning(self, "Sadzby", str(e))
            lines = []
        plates = {v.id: v.plate for v in repo.list_vehicles(self.conn, include_inactive=True)}
        self.table.setRowCount(len(lines))
        for i, l in enumerate(lines):
            t = l.trip
            cells = [
                f"{t.start:%d.%m.%Y %H:%M}", f"{t.end:%d.%m.%Y %H:%M}", t.origin, t.destination,
                t.purpose, plates.get(t.vehicle_id, ""), _num(t.km, 1), _num(t.fuel_price, 3),
                _num(l.meal) + (" *" if t.meal_manual is not None else ""),
                _num(l.flat), _num(l.fuel), _num(l.total),
            ]
            for col, text in enumerate(cells):
                self.table.setItem(i, col, _item(text, t if col == 0 else None))
        meal = sum(l.meal for l in lines)
        comp = sum(l.total for l in lines)
        km = sum(l.trip.km for l in lines)
        self.summary.setText(
            f"{len(lines)} ciest · {_num(km, 0)} km · stravné {_num(meal)} € · "
            f"náhrady za auto {_num(comp)} € · spolu {_num(meal + comp)} €"
        )

    # ------------------------------------------------------------ akcie

    def _selected(self) -> dom.DomesticTrip | None:
        row = self.table.currentRow()
        return self.table.item(row, 0).data(Qt.UserRole) if row >= 0 else None

    def _open(self, trip: dom.DomesticTrip) -> None:
        if TripDialog(self, self.conn, trip).exec():
            self.load()

    def _new_trip(self) -> dom.DomesticTrip:
        y, m = self._ym()
        today = date.today()
        day = today if (today.year, today.month) == (y, m) else date(y, m, 1)
        start = datetime(day.year, day.month, day.day, 7, 0)
        vehicles = repo.list_vehicles(self.conn)
        return dom.DomesticTrip(
            vehicle_id=vehicles[0].id if vehicles else None,
            start=start, end=start + timedelta(hours=2),
            origin=self._home_town(), destination="", km=0,
            fuel_price=dom.last_fuel_price(self.conn) or 0,
        )

    def _home_town(self) -> str:
        # posledné východisko cesty – zvyčajne bydlisko
        row = self.conn.execute(
            "SELECT origin FROM domestic_trips ORDER BY start DESC, id DESC LIMIT 1"
        ).fetchone()
        return row["origin"] if row else ""

    def add(self) -> None:
        if not repo.list_vehicles(self.conn):
            QMessageBox.information(self, "Vozidlo", "Najprv pridajte vozidlo v Nastavenia → Vozidlá.")
            return
        self._open(self._new_trip())

    def edit(self) -> None:
        t = self._selected()
        if t:
            self._open(replace(t))

    def add_return(self) -> None:
        t = self._selected()
        if not t:
            return
        duration = t.end - t.start
        start = t.end + timedelta(hours=1)
        self._open(replace(t, id=None, origin=t.destination, destination=t.origin,
                           start=start, end=start + duration, meal_manual=None))

    def copy(self) -> None:
        t = self._selected()
        if not t:
            return
        shift = timedelta(days=7)
        self._open(replace(t, id=None, start=t.start + shift, end=t.end + shift, meal_manual=None))

    def delete(self) -> None:
        t = self._selected()
        if t and QMessageBox.question(
            self, "Zmazať", f"Zmazať cestu {t.origin} → {t.destination} ({t.start:%d.%m.%Y})?"
        ) == QMessageBox.Yes:
            dom.delete_trip(self.conn, t.id)
            self.load()

    def export(self) -> None:
        y, m = self._ym()
        try:
            sheets = dom.month_sheets(self.conn, y, m)
        except LookupError as e:
            QMessageBox.warning(self, "Export", str(e))
            return
        if not sheets:
            QMessageBox.information(self, "Export", "V tomto mesiaci nie sú žiadne cesty.")
            return
        dlg = ExportDialog(self, y, m)
        if not dlg.exec():
            return
        yearly = dlg.year_mode.isChecked()
        name = exp.default_filename(y, None if yearly else m)
        start_dir = Path.home() / "Documents"
        if yearly:
            path, _ = QFileDialog.getSaveFileName(
                self, "Ročný zošit (existujúci alebo nový)", str(start_dir / name),
                "Excel (*.xlsx)", options=QFileDialog.DontConfirmOverwrite,
            )
        else:
            path, _ = QFileDialog.getSaveFileName(self, "Uložiť export", str(start_dir / name), "Excel (*.xlsx)")
        if not path:
            return
        profile = repo.get_profile(self.conn)
        try:
            if yearly:
                exp.export_into_year_workbook(path, sheets, profile)
            else:
                exp.export_month_file(path, sheets, profile)
        except PermissionError:
            QMessageBox.warning(self, "Export", "Súbor sa nedá uložiť. Nie je otvorený v Exceli?")
            return
        QMessageBox.information(self, "Export", f"Uložené do:\n{path}")
