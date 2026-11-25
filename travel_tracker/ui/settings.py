"""Nastavenia: profil zamestnanca a firmy, vozidlá, sadzby."""

from __future__ import annotations

import sqlite3
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import repository as repo

MONTH_NAMES = ["Január", "Február", "Marec", "Apríl", "Máj", "Jún",
               "Júl", "August", "September", "Október", "November", "December"]


def _money_spin(decimals: int = 2, maximum: float = 10000.0) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setDecimals(decimals)
    s.setMaximum(maximum)
    s.setLocale(s.locale())
    return s


def _date_edit(value: str | None = None) -> QDateEdit:
    d = QDateEdit()
    d.setCalendarPopup(True)
    d.setDisplayFormat("dd.MM.yyyy")
    d.setDate(QDate.fromString(value, "yyyy-MM-dd") if value else QDate.currentDate())
    return d


def _fmt_date(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d.%m.%Y")


def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    return t


def _item(value, data=None) -> QTableWidgetItem:
    it = QTableWidgetItem(str(value))
    if data is not None:
        it.setData(Qt.UserRole, data)
    return it


def _num(x: float, decimals: int = 2) -> str:
    return f"{x:.{decimals}f}".replace(".", ",")


# ====================================================================== profil

class ProfileTab(QWidget):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.conn = conn
        self.fields: dict[str, QLineEdit] = {}

        emp = QGroupBox("Zamestnanec")
        ef = QFormLayout(emp)
        for key, label in [
            ("title", "Titul:"),
            ("first_name", "Meno:"),
            ("last_name", "Priezvisko:"),
            ("address", "Bydlisko:"),
        ]:
            self.fields[key] = QLineEdit()
            ef.addRow(label, self.fields[key])

        comp = QGroupBox("Zamestnávateľ")
        cf = QFormLayout(comp)
        for key, label in [
            ("company_name", "Názov firmy:"),
            ("company_street", "Ulica:"),
            ("company_city", "PSČ a mesto:"),
        ]:
            self.fields[key] = QLineEdit()
            cf.addRow(label, self.fields[key])

        save = QPushButton("Uložiť profil")
        save.clicked.connect(self.save)

        lay = QVBoxLayout(self)
        lay.addWidget(emp)
        lay.addWidget(comp)
        lay.addWidget(save, alignment=Qt.AlignRight)
        lay.addStretch()
        self.load()

    def load(self) -> None:
        p = repo.get_profile(self.conn)
        for key, edit in self.fields.items():
            edit.setText(getattr(p, key))

    def save(self) -> None:
        p = repo.Profile(**{k: e.text().strip() for k, e in self.fields.items()})
        repo.save_profile(self.conn, p)
        QMessageBox.information(self, "Profil", "Profil bol uložený.")


# ====================================================================== vozidlá

class VehicleDialog(QDialog):
    def __init__(self, parent, vehicle: repo.Vehicle | None = None):
        super().__init__(parent)
        self.setWindowTitle("Vozidlo")
        self.vehicle = vehicle or repo.Vehicle(plate="", consumption_l_100km=0)

        self.plate = QLineEdit(self.vehicle.plate)
        self.name = QLineEdit(self.vehicle.name)
        self.name.setPlaceholderText("napr. Volkswagen Passat Variant")
        self.consumption = _money_spin(2, 50)
        self.consumption.setSuffix(" l/100 km")
        self.consumption.setValue(self.vehicle.consumption_l_100km)
        self.fuel = QComboBox()
        self.fuel.addItems(["nafta", "benzín", "LPG", "CNG", "elektrina"])
        self.fuel.setCurrentText(self.vehicle.fuel_type)
        self.default = QCheckBox("Predvolené vozidlo")
        self.default.setChecked(self.vehicle.is_default)

        form = QFormLayout()
        form.addRow("ŠPZ:", self.plate)
        form.addRow("Vozidlo:", self.name)
        form.addRow("Spotreba (podľa TP):", self.consumption)
        form.addRow("Palivo:", self.fuel)
        form.addRow("", self.default)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def result_vehicle(self) -> repo.Vehicle:
        v = self.vehicle
        v.plate = self.plate.text()
        v.name = self.name.text().strip()
        v.consumption_l_100km = self.consumption.value()
        v.fuel_type = self.fuel.currentText()
        v.is_default = self.default.isChecked()
        return v


class VehiclesTab(QWidget):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.conn = conn
        self.table = _table(["ŠPZ", "Vozidlo", "Spotreba l/100 km", "Palivo", "Predvolené"])
        self.table.doubleClicked.connect(self.edit)

        add = QPushButton("Pridať")
        add.clicked.connect(self.add)
        edit = QPushButton("Upraviť")
        edit.clicked.connect(self.edit)
        remove = QPushButton("Vyradiť")
        remove.setToolTip("Vozidlo sa skryje, staré cesty si ho ponechajú.")
        remove.clicked.connect(self.remove)

        buttons = QHBoxLayout()
        for b in (add, edit, remove):
            buttons.addWidget(b)
        buttons.addStretch()

        lay = QVBoxLayout(self)
        lay.addWidget(self.table)
        lay.addLayout(buttons)
        self.load()

    def load(self) -> None:
        vehicles = repo.list_vehicles(self.conn)
        self.table.setRowCount(len(vehicles))
        for i, v in enumerate(vehicles):
            self.table.setItem(i, 0, _item(v.plate, v))
            self.table.setItem(i, 1, _item(v.name))
            self.table.setItem(i, 2, _item(_num(v.consumption_l_100km)))
            self.table.setItem(i, 3, _item(v.fuel_type))
            self.table.setItem(i, 4, _item("áno" if v.is_default else ""))

    def _selected(self) -> repo.Vehicle | None:
        row = self.table.currentRow()
        return self.table.item(row, 0).data(Qt.UserRole) if row >= 0 else None

    def _run(self, vehicle: repo.Vehicle | None) -> None:
        dlg = VehicleDialog(self, vehicle)
        if dlg.exec():
            try:
                repo.save_vehicle(self.conn, dlg.result_vehicle())
            except ValueError as e:
                QMessageBox.warning(self, "Vozidlo", str(e))
            self.load()

    def add(self) -> None:
        self._run(None)

    def edit(self) -> None:
        v = self._selected()
        if v:
            self._run(v)

    def remove(self) -> None:
        v = self._selected()
        if v and QMessageBox.question(self, "Vyradiť", f"Vyradiť vozidlo {v.plate}?") == QMessageBox.Yes:
            repo.deactivate_vehicle(self.conn, v.id)
            self.load()


# ====================================================================== sadzby

class DomesticRatesDialog(QDialog):
    def __init__(self, parent, rates: repo.DomesticRates | None = None):
        super().__init__(parent)
        self.setWindowTitle("Tuzemské sadzby")
        self.rates = rates or repo.DomesticRates(
            valid_from=date.today().isoformat(), km_rate=0, meal_5_12=0, meal_12_18=0, meal_over_18=0
        )
        self.valid_from = _date_edit(self.rates.valid_from)
        self.km = _money_spin(3, 10)
        self.km.setSuffix(" €/km")
        self.km.setValue(self.rates.km_rate)
        self.m1, self.m2, self.m3 = _money_spin(), _money_spin(), _money_spin()
        for spin, val in ((self.m1, self.rates.meal_5_12), (self.m2, self.rates.meal_12_18), (self.m3, self.rates.meal_over_18)):
            spin.setSuffix(" €")
            spin.setValue(val)

        form = QFormLayout()
        form.addRow("Platné od:", self.valid_from)
        form.addRow("Základná náhrada za km:", self.km)
        form.addRow("Stravné 5 – 12 hod.:", self.m1)
        form.addRow("Stravné 12 – 18 hod.:", self.m2)
        form.addRow("Stravné nad 18 hod.:", self.m3)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def result_rates(self) -> repo.DomesticRates:
        r = self.rates
        r.valid_from = self.valid_from.date().toString("yyyy-MM-dd")
        r.km_rate = self.km.value()
        r.meal_5_12, r.meal_12_18, r.meal_over_18 = self.m1.value(), self.m2.value(), self.m3.value()
        return r


class ForeignRateDialog(QDialog):
    def __init__(self, parent, rate: repo.ForeignRate | None = None):
        super().__init__(parent)
        self.setWindowTitle("Zahraničné stravné")
        self.rate = rate or repo.ForeignRate(country="", currency="EUR", daily_rate=0, valid_from=date.today().isoformat())
        self.country = QLineEdit(self.rate.country)
        self.currency = QLineEdit(self.rate.currency)
        self.currency.setMaxLength(3)
        self.daily = _money_spin()
        self.daily.setValue(self.rate.daily_rate)
        self.valid_from = _date_edit(self.rate.valid_from)

        form = QFormLayout()
        form.addRow("Krajina:", self.country)
        form.addRow("Mena:", self.currency)
        form.addRow("Sadzba za deň (100 %, nad 12 hod.):", self.daily)
        form.addRow("Platné od:", self.valid_from)
        form.addRow(QLabel("Do 6 hod. sa počíta 25 %, 6 – 12 hod. 50 %, nad 12 hod. 100 %."))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def result_rate(self) -> repo.ForeignRate:
        r = self.rate
        r.country = self.country.text().strip()
        r.currency = self.currency.text()
        r.daily_rate = self.daily.value()
        r.valid_from = self.valid_from.date().toString("yyyy-MM-dd")
        return r


class RatesTab(QWidget):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.conn = conn

        dom = QGroupBox("Tuzemské sadzby (náhrada za km a stravné)")
        self.dom_table = _table(["Platné od", "€/km", "5 – 12 h", "12 – 18 h", "nad 18 h"])
        self.dom_table.doubleClicked.connect(self.edit_dom)
        dl = QVBoxLayout(dom)
        dl.addWidget(self.dom_table)
        dl.addLayout(self._buttons(self.add_dom, self.edit_dom, self.delete_dom))

        frn = QGroupBox("Zahraničné stravné podľa krajín")
        self.frn_table = _table(["Krajina", "Mena", "Sadzba 100 %", "Platné od"])
        self.frn_table.doubleClicked.connect(self.edit_frn)
        fl = QVBoxLayout(frn)
        fl.addWidget(self.frn_table)
        fl.addLayout(self._buttons(self.add_frn, self.edit_frn, self.delete_frn))

        note = QLabel(
            "Sadzby sa menia opatreniami MPSVR SR (tuzemské) a MF SR (zahraničné). "
            "Pri zmene pridajte nový riadok s dátumom platnosti; staré cesty si ponechajú pôvodné sadzby."
        )
        note.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.addWidget(note)
        lay.addWidget(dom)
        lay.addWidget(frn)
        self.load()

    @staticmethod
    def _buttons(add, edit, delete) -> QHBoxLayout:
        h = QHBoxLayout()
        for label, fn in (("Pridať", add), ("Upraviť", edit), ("Odstrániť", delete)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            h.addWidget(b)
        h.addStretch()
        return h

    def load(self) -> None:
        dom = repo.list_domestic_rates(self.conn)
        self.dom_table.setRowCount(len(dom))
        for i, r in enumerate(dom):
            self.dom_table.setItem(i, 0, _item(_fmt_date(r.valid_from), r))
            self.dom_table.setItem(i, 1, _item(_num(r.km_rate, 3)))
            self.dom_table.setItem(i, 2, _item(_num(r.meal_5_12)))
            self.dom_table.setItem(i, 3, _item(_num(r.meal_12_18)))
            self.dom_table.setItem(i, 4, _item(_num(r.meal_over_18)))
        frn = repo.list_foreign_rates(self.conn)
        self.frn_table.setRowCount(len(frn))
        for i, r in enumerate(frn):
            self.frn_table.setItem(i, 0, _item(r.country, r))
            self.frn_table.setItem(i, 1, _item(r.currency))
            self.frn_table.setItem(i, 2, _item(_num(r.daily_rate)))
            self.frn_table.setItem(i, 3, _item(_fmt_date(r.valid_from)))

    @staticmethod
    def _selected(table: QTableWidget):
        row = table.currentRow()
        return table.item(row, 0).data(Qt.UserRole) if row >= 0 else None

    def _save(self, fn, obj) -> None:
        try:
            fn(self.conn, obj)
        except (ValueError, sqlite3.IntegrityError) as e:
            msg = "Pre tento dátum už sadzba existuje." if isinstance(e, sqlite3.IntegrityError) else str(e)
            QMessageBox.warning(self, "Sadzby", msg)
        self.load()

    def add_dom(self) -> None:
        latest = repo.list_domestic_rates(self.conn)
        template = None
        if latest:
            l = latest[0]
            template = repo.DomesticRates(date.today().isoformat(), l.km_rate, l.meal_5_12, l.meal_12_18, l.meal_over_18)
        dlg = DomesticRatesDialog(self, template)
        if dlg.exec():
            self._save(repo.save_domestic_rates, dlg.result_rates())

    def edit_dom(self) -> None:
        r = self._selected(self.dom_table)
        if r:
            dlg = DomesticRatesDialog(self, r)
            if dlg.exec():
                self._save(repo.save_domestic_rates, dlg.result_rates())

    def delete_dom(self) -> None:
        r = self._selected(self.dom_table)
        if r and QMessageBox.question(self, "Odstrániť", f"Odstrániť sadzby platné od {_fmt_date(r.valid_from)}?") == QMessageBox.Yes:
            self._save(lambda c, x: repo.delete_domestic_rates(c, x.id), r)

    def add_frn(self) -> None:
        dlg = ForeignRateDialog(self)
        if dlg.exec():
            self._save(repo.save_foreign_rate, dlg.result_rate())

    def edit_frn(self) -> None:
        r = self._selected(self.frn_table)
        if r:
            dlg = ForeignRateDialog(self, r)
            if dlg.exec():
                self._save(repo.save_foreign_rate, dlg.result_rate())

    def delete_frn(self) -> None:
        r = self._selected(self.frn_table)
        if r and QMessageBox.question(self, "Odstrániť", f"Odstrániť sadzbu pre {r.country}?") == QMessageBox.Yes:
            self._save(lambda c, x: repo.delete_foreign_rate(c, x.id), r)


class SettingsWidget(QTabWidget):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.addTab(ProfileTab(conn), "Profil")
        self.addTab(VehiclesTab(conn), "Vozidlá")
        self.addTab(RatesTab(conn), "Sadzby")
