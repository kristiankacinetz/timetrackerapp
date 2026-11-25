"""Záložka Zahraničné cesty: zoznam ciest, editor cesty a export cestovného príkazu."""

from __future__ import annotations

import copy
import sqlite3
from datetime import date, time, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .. import export_foreign as exp
from .. import foreign as fx
from .. import repository as repo
from .settings import _date_edit, _item, _money_spin, _num, _table


def _qd(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _pd(q: QDate) -> date:
    return date(q.year(), q.month(), q.day())


def _date(d: date) -> QDateEdit:
    e = _date_edit(d.isoformat())
    return e


class _OptionalTime(QWidget):
    """Čas, ktorý sa dá vynechať (napr. pri ceste autom bez presného času)."""

    def __init__(self, value: time | None):
        super().__init__()
        self.enabled = QCheckBox()
        self.edit = QTimeEdit(QTime(value.hour, value.minute) if value else QTime(8, 0))
        self.edit.setDisplayFormat("HH:mm")
        self.enabled.setChecked(value is not None)
        self.edit.setEnabled(value is not None)
        self.enabled.toggled.connect(self.edit.setEnabled)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.enabled)
        lay.addWidget(self.edit)
        lay.addStretch()

    def value(self) -> time | None:
        if not self.enabled.isChecked():
            return None
        t = self.edit.time()
        return time(t.hour(), t.minute())


class SegmentDialog(QDialog):
    def __init__(self, parent, seg: fx.Segment):
        super().__init__(parent)
        self.setWindowTitle("Úsek cesty")
        self.transport = QComboBox()
        self.transport.setEditable(True)
        self.transport.addItems(fx.TRANSPORTS)
        self.transport.setCurrentText(seg.transport)
        self.from_place = QLineEdit(seg.from_place)
        self.to_place = QLineEdit(seg.to_place)
        self.depart_date, self.arrive_date = _date(seg.depart_date), _date(seg.arrive_date)
        self.depart_time, self.arrive_time = _OptionalTime(seg.depart_time), _OptionalTime(seg.arrive_time)
        self.depart_date.dateChanged.connect(
            lambda q: self.arrive_date.setDate(q) if self.arrive_date.date() < q else None)
        self.km = _money_spin(0, 20000)
        self.km.setSuffix(" km")
        self.km.setValue(seg.km or 0)

        form = QFormLayout()
        form.addRow("Dopravný prostriedok:", self.transport)
        form.addRow("Odkiaľ:", self.from_place)
        form.addRow("Dátum odchodu:", self.depart_date)
        form.addRow("Čas odchodu:", self.depart_time)
        form.addRow("Kam:", self.to_place)
        form.addRow("Dátum príchodu:", self.arrive_date)
        form.addRow("Čas príchodu:", self.arrive_time)
        form.addRow("Km (nepovinné):", self.km)
        hint = QLabel("Ak čas nezaškrtnete, pri výpočte diét sa ráta celý deň.")
        hint.setStyleSheet("color: gray")
        form.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def result_segment(self) -> fx.Segment:
        return fx.Segment(
            transport=self.transport.currentText().strip(), from_place=self.from_place.text().strip(),
            depart_date=_pd(self.depart_date.date()), to_place=self.to_place.text().strip(),
            arrive_date=_pd(self.arrive_date.date()), depart_time=self.depart_time.value(),
            arrive_time=self.arrive_time.value(), km=self.km.value() or None,
        )

    def _accept(self) -> None:
        s = self.result_segment()
        if not s.transport or not s.from_place or not s.to_place:
            QMessageBox.warning(self, "Úsek", "Vyplňte dopravný prostriedok, odkiaľ a kam.")
        elif s.arrive <= s.depart:
            QMessageBox.warning(self, "Úsek", "Príchod musí byť po odchode.")
        else:
            self.accept()


class ExpenseDialog(QDialog):
    def __init__(self, parent, e: fx.Expense):
        super().__init__(parent)
        self.setWindowTitle("Výdavok")
        self.category = QComboBox()
        for key, label in fx.CATEGORIES.items():
            self.category.addItem(label, key)
        self.category.setCurrentIndex(self.category.findData(e.category))
        self.day = _date(e.day)
        self.description = QLineEdit(e.description)
        self.amount = _money_spin(2, 1_000_000)
        self.amount.setSuffix(" €")
        self.amount.setValue(e.amount_eur)
        self.attachment = QLineEdit(e.attachment or "")
        browse = QPushButton("…")
        browse.setFixedWidth(32)
        browse.clicked.connect(self._browse)
        att = QHBoxLayout()
        att.addWidget(self.attachment)
        att.addWidget(browse)

        form = QFormLayout()
        form.addRow("Kategória:", self.category)
        form.addRow("Dátum:", self.day)
        form.addRow("Popis:", self.description)
        form.addRow("Suma v EUR:", self.amount)
        form.addRow("Doklad (PDF):", att)
        hint = QLabel("„Hradené firmou / partnerom“ sa uvedie v príkaze, ale nepripočíta sa k nárokom.")
        hint.setStyleSheet("color: gray")
        hint.setWordWrap(True)
        form.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Doklad", str(Path.home() / "Documents"),
                                              "Doklady (*.pdf *.PDF *.jpg *.png);;Všetky súbory (*)")
        if path:
            self.attachment.setText(path)

    def result_expense(self) -> fx.Expense:
        return fx.Expense(self.category.currentData(), _pd(self.day.date()),
                          self.description.text().strip(), self.amount.value(),
                          self.attachment.text().strip() or None)

    def _accept(self) -> None:
        if not self.description.text().strip() or self.amount.value() <= 0:
            QMessageBox.warning(self, "Výdavok", "Vyplňte popis a sumu.")
        else:
            self.accept()


class TripEditor(QDialog):
    def __init__(self, parent, conn: sqlite3.Connection, trip: fx.ForeignTrip):
        super().__init__(parent)
        self.conn = conn
        self.trip = copy.deepcopy(trip)
        self.setWindowTitle("Zahraničná pracovná cesta")
        self.resize(900, 560)

        tabs = QTabWidget()
        tabs.addTab(self._basic_tab(), "Základné údaje")
        tabs.addTab(self._segments_tab(), "Úseky cesty")
        tabs.addTab(self._allowance_tab(), "Diéty")
        tabs.addTab(self._expenses_tab(), "Ubytovanie a výdavky")
        tabs.currentChanged.connect(lambda _: self._refresh_allowance())

        self.summary = QLabel()
        self.summary.setStyleSheet("font-weight: bold")
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Uložiť")
        buttons.button(QDialogButtonBox.Cancel).setText("Zrušiť")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(self.summary)
        bottom.addStretch()
        bottom.addWidget(buttons)

        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addLayout(bottom)
        self._load_segments()
        self._load_expenses()
        self._refresh_allowance()

    # ------------------------------------------------------------ základné

    def _basic_tab(self) -> QWidget:
        w = QWidget()
        t = self.trip
        self.country = QComboBox()
        countries = sorted({r.country for r in repo.list_foreign_rates(self.conn)})
        self.country.addItems(countries)
        if t.country and t.country not in countries:
            self.country.addItem(t.country)
        self.country.setCurrentText(t.country)
        self.country.currentTextChanged.connect(lambda _: self._refresh_allowance())
        self.place = QLineEdit(t.place)
        self.place.setPlaceholderText("napr. Bern, Švajčiarsko")
        self.purpose = QLineEdit(t.purpose)
        self.purpose.setPlaceholderText("napr. Pracovné stretnutie")
        self.rate = _money_spin(4, 100000)
        self.rate.setValue(t.exchange_rate)
        self.rate.valueChanged.connect(lambda _: self._refresh_allowance())
        self.rate_date = _date(t.rate_date or date.today())
        self.prepayment = QLineEdit(t.prepayment)
        self.advance = _money_spin(2, 1_000_000)
        self.advance.setSuffix(" €")
        self.advance.setValue(t.advance_eur)
        self.advance.valueChanged.connect(lambda _: self._refresh_allowance())
        self.currency_label = QLabel()

        form = QFormLayout(w)
        form.addRow("Krajina:", self.country)
        form.addRow("Miesto pobytu:", self.place)
        form.addRow("Účel cesty:", self.purpose)
        rate_row = QHBoxLayout()
        rate_row.addWidget(self.rate)
        rate_row.addWidget(self.currency_label)
        rate_row.addWidget(QLabel("  k dátumu"))
        rate_row.addWidget(self.rate_date)
        rate_row.addStretch()
        form.addRow("Kurz ECB (1 EUR =):", rate_row)
        form.addRow("Preddavky:", self.prepayment)
        form.addRow("Záloha / prídel valút:", self.advance)
        hint = QLabel("Krajiny a sadzby diét sa nastavujú v Nastavenia → Sadzby. "
                      "Kurz zadajte podľa kurzového lístka ECB (pri krajinách s diétami v EUR sa nepoužije).")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray")
        form.addRow(hint)
        return w

    # ------------------------------------------------------------ úseky

    def _segments_tab(self) -> QWidget:
        w = QWidget()
        self.seg_table = _table(["Dopr. prostr.", "Odkiaľ", "Odchod", "Kam", "Príchod", "km"])
        self.seg_table.doubleClicked.connect(self._edit_segment)
        lay = QVBoxLayout(w)
        lay.addWidget(self.seg_table)
        lay.addLayout(self._buttons((
            ("Pridať úsek", self._add_segment), ("Upraviť", self._edit_segment),
            ("Pridať cestu späť", self._add_return), ("Odstrániť", self._delete_segment))))
        return w

    @staticmethod
    def _buttons(items) -> QHBoxLayout:
        h = QHBoxLayout()
        for label, fn in items:
            b = QPushButton(label)
            b.clicked.connect(fn)
            h.addWidget(b)
        h.addStretch()
        return h

    @staticmethod
    def _when(d: date, t: time | None) -> str:
        return f"{d:%d.%m.%Y}" + (f" {t:%H:%M}" if t else "")

    def _load_segments(self) -> None:
        self.trip.segments.sort(key=lambda s: s.depart)
        segs = self.trip.segments
        self.seg_table.setRowCount(len(segs))
        for i, s in enumerate(segs):
            for col, text in enumerate((s.transport, s.from_place, self._when(s.depart_date, s.depart_time),
                                        s.to_place, self._when(s.arrive_date, s.arrive_time),
                                        _num(s.km, 0) if s.km else "")):
                self.seg_table.setItem(i, col, _item(text))
        self._refresh_allowance()

    def _segment_dialog(self, seg: fx.Segment, index: int | None) -> None:
        dlg = SegmentDialog(self, seg)
        if dlg.exec():
            if index is None:
                self.trip.segments.append(dlg.result_segment())
            else:
                self.trip.segments[index] = dlg.result_segment()
            self._load_segments()

    def _add_segment(self) -> None:
        if self.trip.segments:
            last = self.trip.segments[-1]
            seg = fx.Segment(last.transport, last.to_place, last.arrive_date, "", last.arrive_date)
        else:
            seg = fx.Segment("Auto", "", date.today(), "", date.today())
        self._segment_dialog(seg, None)

    def _edit_segment(self) -> None:
        i = self.seg_table.currentRow()
        if i >= 0:
            self._segment_dialog(self.trip.segments[i], i)

    def _add_return(self) -> None:
        """Pridá spiatočné úseky v opačnom poradí (dátum treba upraviť)."""
        if not self.trip.segments:
            return
        last_day = self.trip.date_to + timedelta(days=1)
        back = [fx.Segment(s.transport, s.to_place, last_day, s.from_place, last_day, None, None, s.km)
                for s in reversed(self.trip.segments)]
        self.trip.segments.extend(back)
        self._load_segments()
        QMessageBox.information(self, "Cesta späť",
                                f"Pridal som {len(back)} úsekov späť s dátumom {last_day:%d.%m.%Y}. "
                                "Upravte dátumy a časy podľa skutočnosti.")

    def _delete_segment(self) -> None:
        i = self.seg_table.currentRow()
        if i >= 0:
            del self.trip.segments[i]
            self._load_segments()

    # ------------------------------------------------------------ diéty

    def _allowance_tab(self) -> QWidget:
        w = QWidget()
        self.allow_table = _table(["Dátum", "Hodín na ceste", "Percento", "Suma (mena)", "Suma EUR"])
        self.allow_info = QLabel()
        self.allow_info.setWordWrap(True)
        lay = QVBoxLayout(w)
        lay.addWidget(self.allow_info)
        lay.addWidget(self.allow_table)
        hint = QLabel("Percento sa počíta automaticky (do 6 h 25 %, 6 – 12 h 50 %, nad 12 h 100 %). "
                      "Ak treba, zmeňte ho v stĺpci Percento, napr. pri bezplatnej strave.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray")
        lay.addWidget(hint)
        return w

    def _apply_basic(self) -> None:
        t = self.trip
        t.country = self.country.currentText()
        t.place = self.place.text().strip()
        t.purpose = self.purpose.text().strip()
        t.exchange_rate = self.rate.value()
        t.rate_date = _pd(self.rate_date.date())
        t.prepayment = self.prepayment.text().strip()
        t.advance_eur = self.advance.value()

    def _refresh_allowance(self) -> None:
        if not hasattr(self, "allow_table") or not hasattr(self, "country"):
            return
        self._apply_basic()
        self.allow_table.setRowCount(0)
        try:
            s = fx.settle(self.conn, self.trip)
        except (ValueError, LookupError) as e:
            self.allow_info.setText(str(e))
            self.summary.setText("")
            self.currency_label.setText("")
            return
        self.currency_label.setText(s.currency)
        self.rate.setEnabled(s.currency != "EUR")
        self.allow_info.setText(f"{self.trip.country}: denná sadzba {_num(s.daily_rate)} {s.currency}")
        self.allow_table.setRowCount(len(s.days))
        for i, d in enumerate(s.days):
            self.allow_table.setItem(i, 0, _item(f"{d.day:%d.%m.%Y}"))
            self.allow_table.setItem(i, 1, _item(_num(d.hours, 1)))
            combo = QComboBox()
            for p in (0, 25, 50, 100):
                combo.addItem(f"{p} %", p)
            combo.setCurrentIndex(combo.findData(d.percent))
            if d.overridden:
                combo.setStyleSheet("font-weight: bold")
            combo.currentIndexChanged.connect(lambda _, day=d.day, c=combo: self._override(day, c.currentData()))
            self.allow_table.setCellWidget(i, 2, combo)
            self.allow_table.setItem(i, 3, _item(f"{_num(d.amount_foreign)} {s.currency}"))
            self.allow_table.setItem(i, 4, _item(_num(d.amount_eur)))
        verb = "dostane pracovník" if s.to_pay >= 0 else "vráti pracovník"
        self.summary.setText(
            f"Diéty {_num(s.allowance_eur)} € · ubytovanie {_num(s.accommodation)} € · "
            f"ostatné {_num(s.other)} € · {verb} {_num(abs(s.to_pay))} €")

    def _override(self, day: date, percent: int) -> None:
        days = fx.allowance_days(fx.ForeignTrip("", "", "", segments=self.trip.segments), "EUR", 100)
        auto = next((d.percent for d in days if d.day == day), None)
        if percent == auto:
            self.trip.day_overrides.pop(day, None)
        else:
            self.trip.day_overrides[day] = percent
        self._refresh_allowance()

    # ------------------------------------------------------------ výdavky

    def _expenses_tab(self) -> QWidget:
        w = QWidget()
        self.exp_table = _table(["Kategória", "Dátum", "Popis", "Suma EUR", "Doklad"])
        self.exp_table.doubleClicked.connect(self._edit_expense)
        lay = QVBoxLayout(w)
        lay.addWidget(self.exp_table)
        lay.addLayout(self._buttons((("Pridať", self._add_expense), ("Upraviť", self._edit_expense),
                                     ("Odstrániť", self._delete_expense))))
        return w

    def _load_expenses(self) -> None:
        ex = self.trip.expenses
        self.exp_table.setRowCount(len(ex))
        for i, e in enumerate(ex):
            for col, text in enumerate((fx.CATEGORIES[e.category], f"{e.day:%d.%m.%Y}", e.description,
                                        _num(e.amount_eur), Path(e.attachment).name if e.attachment else "")):
                self.exp_table.setItem(i, col, _item(text))
        self._refresh_allowance()

    def _expense_dialog(self, e: fx.Expense, index: int | None) -> None:
        dlg = ExpenseDialog(self, e)
        if dlg.exec():
            if index is None:
                self.trip.expenses.append(dlg.result_expense())
            else:
                self.trip.expenses[index] = dlg.result_expense()
            self._load_expenses()

    def _add_expense(self) -> None:
        self._expense_dialog(fx.Expense("accommodation", self.trip.date_from or date.today(), "", 0), None)

    def _edit_expense(self) -> None:
        i = self.exp_table.currentRow()
        if i >= 0:
            self._expense_dialog(self.trip.expenses[i], i)

    def _delete_expense(self) -> None:
        i = self.exp_table.currentRow()
        if i >= 0:
            del self.trip.expenses[i]
            self._load_expenses()

    # ------------------------------------------------------------ uloženie

    def _save(self) -> None:
        self._apply_basic()
        if not self.trip.place or not self.trip.purpose:
            QMessageBox.warning(self, "Cesta", "Vyplňte miesto pobytu a účel cesty.")
            return
        try:
            fx.save_trip(self.conn, self.trip)
        except ValueError as e:
            QMessageBox.warning(self, "Cesta", str(e))
            return
        self.accept()


class ForeignTab(QWidget):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.conn = conn
        self.table = _table(["Termín", "Krajina", "Miesto", "Účel", "Doprava", "Diéty €", "Nároky €"])
        self.table.doubleClicked.connect(self.edit)
        buttons = QHBoxLayout()
        for label, fn in (("Nová cesta", self.add), ("Upraviť", self.edit), ("Kopírovať", self.copy),
                          ("Zmazať", self.delete)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            buttons.addWidget(b)
        buttons.addStretch()
        export_btn = QPushButton("Export cestovného príkazu…")
        export_btn.clicked.connect(self.export)
        buttons.addWidget(export_btn)
        lay = QVBoxLayout(self)
        lay.addWidget(self.table)
        lay.addLayout(buttons)
        self.load()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.load()

    def load(self) -> None:
        trips = fx.list_trips(self.conn)
        self.table.setRowCount(len(trips))
        for i, t in enumerate(trips):
            try:
                s = fx.settle(self.conn, t)
                allowance, claims = _num(s.allowance_eur), _num(s.claims)
            except (ValueError, LookupError):
                allowance = claims = "?"
            for col, text in enumerate((t.term(), t.country, t.place, t.purpose, t.transport_summary,
                                        allowance, claims)):
                self.table.setItem(i, col, _item(text, t.id if col == 0 else None))

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        return self.table.item(row, 0).data(Qt.UserRole) if row >= 0 else None

    def add(self) -> None:
        countries = repo.list_foreign_rates(self.conn)
        if not countries:
            QMessageBox.information(self, "Krajiny", "Najprv pridajte krajinu v Nastavenia → Sadzby.")
            return
        trip = fx.ForeignTrip(country=countries[0].country, place="", purpose="Pracovné stretnutie")
        if TripEditor(self, self.conn, trip).exec():
            self.load()

    def edit(self) -> None:
        tid = self._selected_id()
        if tid and TripEditor(self, self.conn, fx.load_trip(self.conn, tid)).exec():
            self.load()

    def copy(self) -> None:
        """Nová cesta podľa vybranej (napr. ďalšia cesta do Bernu); dátumy treba upraviť."""
        tid = self._selected_id()
        if not tid:
            return
        t = fx.load_trip(self.conn, tid)
        t.id = None
        t.expenses = []
        t.day_overrides = {}
        if TripEditor(self, self.conn, t).exec():
            self.load()

    def delete(self) -> None:
        tid = self._selected_id()
        if tid and QMessageBox.question(self, "Zmazať", "Zmazať vybranú cestu?") == QMessageBox.Yes:
            fx.delete_trip(self.conn, tid)
            self.load()

    def export(self) -> None:
        tid = self._selected_id()
        if not tid:
            QMessageBox.information(self, "Export", "Vyberte cestu.")
            return
        trip = fx.load_trip(self.conn, tid)
        try:
            s = fx.settle(self.conn, trip)
        except (ValueError, LookupError) as e:
            QMessageBox.warning(self, "Export", str(e))
            return
        start = Path.home() / "Documents" / exp.default_filename(trip)
        path, _ = QFileDialog.getSaveFileName(self, "Uložiť cestovný príkaz", str(start), "Excel (*.xlsx)")
        if not path:
            return
        try:
            exp.export_trip(path, trip, s, repo.get_profile(self.conn))
        except PermissionError:
            QMessageBox.warning(self, "Export", "Súbor sa nedá uložiť. Nie je otvorený v Exceli?")
            return
        QMessageBox.information(self, "Export", f"Uložené do:\n{path}")
