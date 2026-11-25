"""Export tuzemských ciest do Excelu v rozložení doterajších výkazov.

Hárok sa volá podľa mesiaca (napr. "Február 2026"); pri viacerých vozidlách
v mesiaci sa k názvu pridá ŠPZ. Vzorce zostávajú v súbore, aby ich účtovníčka
videla rovnako ako doteraz.
"""

from __future__ import annotations

import calendar
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from .domestic import MonthSheet
from .repository import Profile

MONTHS = ["Január", "Február", "Marec", "April", "Máj", "Jún",
          "Júl", "August", "September", "Október", "November", "December"]

FONT = "Times New Roman"
_thin = Side(style="thin")
BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
HEADER_FILL = PatternFill("solid", fgColor="FFFFE598")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
FIRST_ROW = 7


def sheet_title(sheet: MonthSheet, with_plate: bool) -> str:
    title = f"{MONTHS[sheet.month - 1]} {sheet.year}"
    if with_plate:
        title += f" {sheet.vehicle.plate}"
    return title[:31]


def write_sheet(ws, sheet: MonthSheet, profile: Profile) -> None:
    driver = " ".join(p for p in (profile.first_name, profile.last_name) if p)
    ws["A1"] = f"{driver} - Cestovné príkazy {sheet.month:02d}/{sheet.year}"
    ws["A1"].font = Font(name=FONT, size=11, bold=True)
    ws["A2"] = f"ŠPZ: {sheet.vehicle.plate}"
    ws["C2"] = f"Vozidlo: {sheet.vehicle.name}"
    ws["F2"] = f"Vodič: {driver}"
    ws["I2"] = f"Bydlisko: {profile.address}"
    for c in ("A2", "C2", "F2", "I2"):
        ws[c].font = Font(name=FONT, size=11)
    ws["A3"] = "Paušálna náhrada za 1 km (€): "
    ws["D3"] = sheet.km_rate
    ws["F3"] = "Spotreba vozidla (l/100km):"
    ws["H3"] = sheet.vehicle.consumption_l_100km
    for c in ("A3", "D3", "F3", "H3"):
        ws[c].font = Font(name=FONT, size=10)
    ws["Q4"] = 100

    # hlavička tabuľky
    headers = {
        "A5": "Začiatok cesty", "C5": "Koniec cesty", "E5": "Odkiaľ", "G5": "Kam",
        "I5": "Dôvod", "J5": "Stravné", "K5": "Počet km", "L5": "Cena PHM  € / liter",
        "M5": "Náhrada (€)", "A6": "Dátum od ", "B6": "Čas 1", "C6": "Dátum do ",
        "D6": "Čas 2", "M6": "Paušálna", "N6": "PHM", "O6": "Spolu",
    }
    for row in (5, 6):
        for col in range(1, 16):
            cell = ws.cell(row, col)
            cell.font = Font(name=FONT, size=9, bold=(col == 10))
            cell.fill = HEADER_FILL
            cell.border = BORDER
            cell.alignment = CENTER
    for ref, text in headers.items():
        ws[ref] = text
    for rng in ("A5:B5", "C5:D5", "E5:F6", "G5:H6", "I5:I6", "J5:J6",
                "K5:K6", "L5:L6", "M5:O5"):
        ws.merge_cells(rng)

    # riadky ciest
    r = FIRST_ROW
    for line in sheet.lines:
        t = line.trip
        # Ak sa sadzba €/km v priebehu mesiaca zmenila, riadok dostane vlastnú hodnotu.
        own_rate = abs(line.flat - t.km * sheet.km_rate) > 1e-9
        flat = f"=K{r}*{line.flat / t.km:.4f}" if own_rate else f"=K{r}*$D$3"
        values = {
            1: t.start.date(), 2: t.start.time(), 3: t.end.date(), 4: t.end.time(),
            5: t.origin, 7: t.destination, 9: t.purpose, 10: round(line.meal, 2),
            11: t.km, 12: t.fuel_price, 13: flat,
            14: f"=($H$3*L{r}/$Q$4)*K{r}", 15: f"=M{r}+N{r}",
        }
        for col in range(1, 16):
            cell = ws.cell(r, col)
            cell.font = Font(name=FONT, size=9)
            cell.border = BORDER
            cell.alignment = CENTER
            if col in values:
                cell.value = values[col]
        ws.cell(r, 1).number_format = ws.cell(r, 3).number_format = "dd.mm.yyyy"
        ws.cell(r, 2).number_format = ws.cell(r, 4).number_format = "h:mm"
        ws.cell(r, 10).number_format = "#,##0.00"
        ws.cell(r, 11).number_format = "#,##0.00"
        ws.cell(r, 12).number_format = "#,##0.000"
        for col in (13, 14, 15):
            ws.cell(r, col).number_format = "#,##0.00"
        ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=6)
        ws.merge_cells(start_row=r, start_column=7, end_row=r, end_column=8)
        r += 1

    last = r - 1
    total_row = r
    ws.cell(total_row, 9, "Súčet")
    for col, letter in ((10, "J"), (11, "K"), (13, "M"), (14, "N"), (15, "O")):
        ws.cell(total_row, col, f"=SUM({letter}{FIRST_ROW}:{letter}{last})")
    for col in range(9, 16):
        c = ws.cell(total_row, col)
        c.font = Font(name=FONT, size=9, bold=True)
        c.border = BORDER
        c.alignment = CENTER
        if col >= 10:
            c.number_format = "#,##0.00"

    month_end = date(sheet.year, sheet.month, calendar.monthrange(sheet.year, sheet.month)[1])
    ws.cell(total_row + 1, 1, "Dátum:")
    ws.cell(total_row + 1, 2, month_end).number_format = "dd.mm.yyyy"
    ws.cell(total_row + 1, 9, "Spolu náhrady:")
    total = ws.cell(total_row + 1, 11, f"=J{total_row}+O{total_row}")
    total.number_format = "#,##0.00"
    total.font = Font(name=FONT, size=9, bold=True)
    ws.cell(total_row + 2, 1, "Podpis spracovateľa:")
    ws.cell(total_row + 2, 9, "Slovom:")
    for row in (total_row + 1, total_row + 2):
        for col in (1, 2, 9):
            ws.cell(row, col).font = Font(name=FONT, size=9)

    widths = {"A": 11, "B": 10, "C": 11, "D": 7, "E": 10, "F": 10, "G": 10, "H": 10,
              "I": 11, "J": 9, "K": 9, "L": 11, "M": 10, "N": 10, "O": 10}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    ws.column_dimensions["Q"].hidden = True  # pomocná bunka Q4 = 100
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def _write_into(wb: Workbook, sheets: list[MonthSheet], profile: Profile) -> None:
    multi = len(sheets) > 1
    for sheet in sheets:
        title = sheet_title(sheet, multi)
        if title in wb.sheetnames:
            del wb[title]
        ws = wb.create_sheet(title)
        write_sheet(ws, sheet, profile)
    # hárky zoradiť chronologicky podľa mesiaca
    def key(ws):
        parts = ws.title.split()
        try:
            return (int(parts[1]), MONTHS.index(parts[0]), ws.title)
        except (IndexError, ValueError):
            return (9999, 99, ws.title)
    wb._sheets.sort(key=key)


def export_month_file(path: Path | str, sheets: list[MonthSheet], profile: Profile) -> Path:
    """Samostatný súbor za mesiac (prepíše existujúci)."""
    if not sheets:
        raise ValueError("V tomto mesiaci nie sú žiadne cesty.")
    wb = Workbook()
    wb.remove(wb.active)
    _write_into(wb, sheets, profile)
    path = Path(path)
    wb.save(path)
    return path


def export_into_year_workbook(path: Path | str, sheets: list[MonthSheet], profile: Profile) -> Path:
    """Pridá (alebo nahradí) hárok mesiaca v ročnom zošite; ak zošit neexistuje, vytvorí ho."""
    if not sheets:
        raise ValueError("V tomto mesiaci nie sú žiadne cesty.")
    path = Path(path)
    if path.exists():
        wb = load_workbook(path)
    else:
        wb = Workbook()
        wb.remove(wb.active)
    _write_into(wb, sheets, profile)
    wb.save(path)
    return path


def default_filename(year: int, month: int | None = None) -> str:
    if month is None:
        return f"Tuzemské cesťáky hromadné {year}.xlsx"
    return f"Tuzemské cesťáky {month:02d}_{year}.xlsx"
