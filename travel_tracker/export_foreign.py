"""Export zahraničnej cesty do Excelu v podobe doterajšieho cestovného príkazu.

Tri hárky ako v pôvodných súboroch:
  Sheet1 – povolenie, úseky cesty a nárok na stravné po dňoch
  Sheet2 – ubytovanie, ostatné výdavky, výdavky hradené firmou/partnerom, vyúčtovanie
  Sheet3 – kurz ECB a sadzby diét 25/50/100 %
Sumy sú vzorce, aby sa dali v Exceli skontrolovať.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter

from .foreign import CATEGORIES, ForeignTrip, Settlement
from .repository import Profile

LABEL = "Arial"
VALUE = "Corsiva"  # "rukopisné" hodnoty ako v pôvodných príkazoch
thin, medium = Side(style="thin"), Side(style="medium")
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
SECTION = Border(left=medium, right=medium, top=medium, bottom=medium)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center")

# riadky stravného na Sheet3
PCT_ROW = {25: 6, 50: 7, 100: 8}


def _put(ws, ref, value, *, bold=False, size=12, font=LABEL, align=None, fmt=None, border=None, merge=None):
    if merge:
        ws.merge_cells(merge)
        if border:
            for row in ws[merge]:
                for c in row:
                    c.border = border
    cell = ws[ref]
    cell.value = value
    cell.font = Font(name=font, size=size, bold=bold)
    if align:
        cell.alignment = align
    if fmt:
        cell.number_format = fmt
    if border and not merge:
        cell.border = border
    return cell


def _sheet1(ws, trip: ForeignTrip, s: Settlement, profile: Profile) -> int:
    """Vráti číslo riadku so súčtom stravného (pre odkaz zo Sheet2)."""
    widths = {"A": 11.3, "B": 18.7, "C": 5.3, "D": 11.3, "E": 8.7, "F": 0.7,
              "G": 13.7, "H": 21.8, "I": 10.9, "J": 13.9}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    _put(ws, "A7", "Povolenie", bold=True, size=14, align=CENTER, merge="A7:J7")
    _put(ws, "A9", profile.company_name, bold=True, align=LEFT, merge="A9:D9")
    _put(ws, "A10", profile.company_street, align=LEFT, merge="A10:D10")
    _put(ws, "A11", profile.company_city, align=LEFT, merge="A11:D11")
    _put(ws, "E9", "Priezvisko, meno, titul:", merge="E9:G9")
    name = f"{profile.title} {profile.last_name} {profile.first_name}".strip()
    _put(ws, "H9", name, bold=True, font=VALUE, align=LEFT, border=BOX, merge="H9:J9")
    _put(ws, "E10", "Účel cesty a miesto pobytu:", merge="E10:H10")
    _put(ws, "E11", f"{trip.purpose}, {trip.place}", bold=True, font=VALUE, align=LEFT, border=BOX, merge="E11:J11")
    _put(ws, "A12", "Termín konania:", align=LEFT, border=BOX, merge="A12:B12")
    _put(ws, "C12", trip.term(), bold=True, font=VALUE, align=CENTER, border=BOX, merge="C12:J12")
    _put(ws, "A13", "Spôsob prepravy:", align=LEFT, border=BOX, merge="A13:B13")
    _put(ws, "C13", trip.transport_summary, bold=True, font=VALUE, align=CENTER, border=BOX, merge="C13:H13")

    _put(ws, "A15", "Požadované vybavenie", bold=True, align=CENTER, border=SECTION, merge="A15:F15")
    _put(ws, "G15", "Prídel valút", bold=True, align=CENTER, border=SECTION, merge="G15:J15")
    for r, label, unit in ((16, "Diéty na", "dní po"), (17, "Ubytovanie na", "nocí po"), (18, "Vreckové na", "dní po")):
        _put(ws, f"A{r}", label)
        _put(ws, f"D{r}", unit)
        _put(ws, f"F{r}", "=")
        _put(ws, f"G{r}", f"=PRODUCT(C{r},E{r})" if r > 16 else 0, font=VALUE, merge=f"G{r}:H{r}")
        _put(ws, f"I{r}", "EUR", merge=f"I{r}:J{r}")
    _put(ws, "A19", "Zúčtovateľná záloha na")
    _put(ws, "F19", "=")
    _put(ws, "G19", trip.advance_eur, font=VALUE, fmt="#,##0.00")
    _put(ws, "H19", "eur")
    _put(ws, "A21", "Dátum a podpis pracovníka, oprávneného povoliť cestu:", merge="A21:J21")
    _put(ws, "A22", "Preddavky:")
    _put(ws, "B22", trip.prepayment, font=VALUE)

    _put(ws, "A24", "Vyúčtovanie valutových prostriedkov", bold=True, align=CENTER, border=SECTION, merge="A24:J24")
    _put(ws, "A25", "Odchod", align=CENTER, border=BOX, merge="A25:F25")
    _put(ws, "G25", "Príchod", align=CENTER, border=BOX, merge="G25:J25")
    for ref, text in (("A26", "Dopr. prostr."), ("B26", "Miesto"), ("C26", "km"), ("D26", "Dátum"),
                      ("E26", "Čas"), ("G26", "Dopr. prostr."), ("H26", "Miesto"), ("I26", "Dátum"), ("J26", "Čas")):
        _put(ws, ref, text, size=10, align=CENTER, border=BOX, merge="E26:F26" if ref == "E26" else None)

    r = 27
    segs = sorted(trip.segments, key=lambda x: x.depart)
    for i in range(max(6, len(segs))):
        seg = segs[i] if i < len(segs) else None
        vals = {
            "A": seg.transport if seg else None, "B": seg.from_place if seg else None,
            "C": seg.km if seg and seg.km else None, "D": seg.depart_date if seg else None,
            "E": seg.depart_time if seg else None, "G": seg.transport if seg else None,
            "H": seg.to_place if seg else None, "I": seg.arrive_date if seg else None,
            "J": seg.arrive_time if seg else None,
        }
        for col, v in vals.items():
            fmt = "dd.mm.yy" if col in "DI" else "h:mm" if col in "EJ" else None
            _put(ws, f"{col}{r}", v, font=VALUE if col in "CDEIJ" else LABEL, align=LEFT if col in "ABGH" else CENTER,
                 fmt=fmt, border=BOX, merge=f"E{r}:F{r}" if col == "E" else None)
        r += 1

    r += 1
    _put(ws, f"A{r}", "Nárok na čerpanie stravného a vreckového", bold=True, align=CENTER, border=SECTION,
         merge=f"A{r}:J{r}")
    r += 1
    first = r
    for d in s.days:
        if r == first:
            _put(ws, f"A{r}", "Dátum:")
        _put(ws, f"B{r}", d.day, bold=True, font=VALUE, align=CENTER, fmt="dd.mm.yy", merge=f"B{r}:C{r}")
        _put(ws, f"D{r}", f"{d.percent} %", font=VALUE, align=CENTER, merge=f"D{r}:F{r}")
        value = f"=Sheet3!D{PCT_ROW[d.percent]}" if d.percent in PCT_ROW else d.amount_eur
        _put(ws, f"G{r}", value, bold=True, font=VALUE, align=CENTER, fmt="0.00", border=BOX, merge=f"G{r}:H{r}")
        _put(ws, f"I{r}", "EUR", merge=f"I{r}:J{r}")
        r += 1
    last = r - 1
    _put(ws, f"A{r}", "Spolu:")
    _put(ws, f"G{r}", f"=SUM(G{first}:G{last})" if s.days else 0, bold=True, font=VALUE, align=CENTER,
         fmt="0.00", border=BOX, merge=f"G{r}:H{r}")
    _put(ws, f"I{r}", "EUR", merge=f"I{r}:J{r}")
    return r


def _expense_block(ws, r: int, title: str, items, total_label: str = "Spolu:") -> tuple[int, int]:
    """Vráti (riadok súčtu, nasledujúci voľný riadok)."""
    _put(ws, f"A{r}", title, bold=True, align=CENTER, border=SECTION, merge=f"A{r}:H{r}")
    r += 1
    _put(ws, f"A{r}", "Dátum:")
    r += 1
    first = r
    for e in items or [None]:
        _put(ws, f"A{r}", e.day if e else None, font=VALUE, fmt="dd.mm.yy", border=BOX)
        _put(ws, f"B{r}", e.description if e else None, font=VALUE, align=LEFT, border=BOX, merge=f"B{r}:D{r}")
        _put(ws, f"E{r}", e.amount_eur if e else None, font=VALUE, align=CENTER, fmt="#,##0.00", border=BOX,
             merge=f"E{r}:F{r}")
        _put(ws, f"G{r}", "EUR" if e else None, merge=f"G{r}:H{r}")
        r += 1
    _put(ws, f"A{r}", total_label)
    _put(ws, f"E{r}", f"=SUM(E{first}:E{r - 1})", bold=True, font=VALUE, align=CENTER, fmt="#,##0.00",
         border=BOX, merge=f"E{r}:F{r}")
    _put(ws, f"G{r}", "EUR", merge=f"G{r}:H{r}")
    return r, r + 2


def _sheet2(ws, trip: ForeignTrip, allowance_total_row: int) -> None:
    for col, w in {"A": 12.1, "B": 10.5, "C": 11.3, "D": 18.5, "E": 11.3}.items():
        ws.column_dimensions[col].width = w

    def items(cat):
        return sorted((e for e in trip.expenses if e.category == cat), key=lambda e: e.day)

    acc_row, r = _expense_block(ws, 2, "Nárok na úhradu ubytovania", items("accommodation"))
    oth_row, r = _expense_block(ws, r, "Nárok na úhradu ostatných výdavkov", items("other"))
    _, r = _expense_block(ws, r, "Výdavky hradené obchodným partnerom", items("paid_by_company"))

    claims = r
    _put(ws, f"A{r}", "Nároky celkom:", align=LEFT, border=BOX, merge=f"A{r}:D{r}")
    _put(ws, f"E{r}", f"=Sheet1!G{allowance_total_row}+E{acc_row}+E{oth_row}", bold=True, font=VALUE,
         align=CENTER, fmt="#,##0.00", border=BOX, merge=f"E{r}:F{r}")
    _put(ws, f"G{r}", "EUR", merge=f"G{r}:H{r}")
    r += 1
    _put(ws, f"A{r}", "Prídel valutových prostriedkov:", align=LEFT, border=BOX, merge=f"A{r}:D{r}")
    _put(ws, f"E{r}", trip.advance_eur, bold=True, font=VALUE, align=CENTER, fmt="#,##0.00", border=BOX,
         merge=f"E{r}:F{r}")
    _put(ws, f"G{r}", "EUR", merge=f"G{r}:H{r}")
    r += 1
    _put(ws, f"A{r}", "Rozdiel:", merge=f"A{r}:A{r + 1}")
    _put(ws, f"B{r}", "vráti pracovník do pokladne", merge=f"B{r}:D{r}")
    _put(ws, f"E{r}", f"=MAX(0,E{claims + 1}-E{claims})", bold=True, font=VALUE, align=CENTER,
         fmt="#,##0.00", border=BOX, merge=f"E{r}:F{r}")
    _put(ws, f"G{r}", "EUR", merge=f"G{r}:H{r}")
    _put(ws, f"B{r + 1}", "dostane pracovník", merge=f"B{r + 1}:D{r + 1}")
    _put(ws, f"E{r + 1}", f"=MAX(0,E{claims}-E{claims + 1})", bold=True, font=VALUE, align=CENTER,
         fmt="#,##0.00", border=BOX, merge=f"E{r + 1}:F{r + 1}")
    _put(ws, f"G{r + 1}", "EUR", merge=f"G{r + 1}:H{r + 1}")
    r += 4
    _put(ws, f"A{r}", "Prehlasujem, že moje údaje sú správne a úplné. Pokiaľ mi strava, resp. ubytovanie "
                      "boli na ZSC poskytnuté zdarma, tak tieto skutočnosti priznávam.",
         size=10, align=Alignment(wrap_text=True, vertical="top"), merge=f"A{r}:H{r + 1}")
    r += 4
    _put(ws, f"A{r}", "Dátum:")
    _put(ws, f"B{r}", trip.date_to, font=VALUE, fmt="dd.mm.yyyy")
    _put(ws, f"E{r}", "Podpis účtujúceho:")
    _put(ws, f"E{r + 1}", "Schválil:")
    _put(ws, f"E{r + 2}", "Podpis pracovníka, ktorý")
    _put(ws, f"E{r + 3}", "vyúčtovanie upravil:")


def _sheet3(ws, trip: ForeignTrip, s: Settlement) -> None:
    ws.column_dimensions["A"].width = 38
    cur = s.currency.upper()
    rate_date = f" k {trip.rate_date:%d.%m.%Y}" if trip.rate_date else ""
    _put(ws, "A1", f"Denný kurzový lístok ECB{rate_date}")
    _put(ws, "A2", f"EUR -> {cur}")
    _put(ws, "B2", trip.exchange_rate if cur != "EUR" else 1)
    _put(ws, "A3", f"{cur} -> EUR")
    _put(ws, "B3", "=1/B2")
    _put(ws, "A5", f"Diéty – {trip.country}")
    for pct, label in ((25, "25% (menej ako 6 hod)"), (50, "50% (6-12 hod)"), (100, "100% (viac ako 12 hod)")):
        r = PCT_ROW[pct]
        _put(ws, f"A{r}", label)
        _put(ws, f"B{r}", s.daily_rate * pct / 100)
        _put(ws, f"C{r}", cur)
        _put(ws, f"D{r}", f"=B{r}*$B$3" if cur != "EUR" else f"=B{r}", fmt="0.00")
        _put(ws, f"E{r}", "EUR")
    _put(ws, "A11", "Prílohy dokladov:")
    attachments = [Path(e.attachment).name for e in trip.expenses if e.attachment]
    for i, name in enumerate(attachments):
        _put(ws, f"A{12 + i}", name, size=10)


def export_trip(path: Path | str, trip: ForeignTrip, settlement: Settlement, profile: Profile) -> Path:
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Sheet1"
    ws2 = wb.create_sheet("Sheet2")
    ws3 = wb.create_sheet("Sheet3")
    total_row = _sheet1(ws1, trip, settlement, profile)
    _sheet2(ws2, trip, total_row)
    _sheet3(ws3, trip, settlement)
    for ws in (ws1, ws2):
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 1
        ws.sheet_properties.pageSetUpPr.fitToPage = True
    path = Path(path)
    wb.save(path)
    return path


def default_filename(trip: ForeignTrip) -> str:
    d = trip.date_from
    place = trip.place.split(",")[0].strip() or trip.country
    return f"Zahraničná pracovná cesta - {d:%m_%Y}_{place}.xlsx"
