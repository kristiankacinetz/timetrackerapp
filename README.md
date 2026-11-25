# Travel Tracker

Lokálna desktopová aplikácia (Windows) na evidenciu pracovných ciest zamestnancov
a export podkladov pre účtovníčku podľa zákona č. 283/2002 Z.z. o cestovných náhradách.

- **Tuzemské cesty** – evidencia ciest autom, výpočet náhrady (paušál za km + PHM) a stravného,
  mesačný export do Excelu (ročný zošit alebo súbor za mesiac).
- **Zahraničné cesty** – cesta s viacerými úsekmi a dopravnými prostriedkami, zahraničné stravné,
  ubytovanie a výdavky, export cestovného príkazu do Excelu.

Každý zamestnanec má aplikáciu na svojom počítači; dáta sú v `%APPDATA%\TravelTracker\data.db`.

## Stav

| Krok | Obsah | Stav |
|---|---|---|
| 1 | Základ aplikácie, profil, vozidlá, sadzby | hotovo |
| 2 | Tuzemské cesty a mesačný export | hotovo |
| 3 | Zahraničné cesty a cestovný príkaz | hotovo |
| 4 | Zabalenie do .exe, overenie na reálnych dátach | pripravuje sa |

## Spustenie (vývoj)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m travel_tracker
```

Testy: `python -m pytest`

## Sadzby

Predvolené sadzby (0,313 €/km; stravné 9,30 / 13,80 / 20,60 €; Švajčiarsko 80 CHF, Poľsko 37 EUR)
si overte v aktuálnych opatreniach MPSVR SR a MF SR a v aplikácii ich upravte v Nastavenia → Sadzby.
