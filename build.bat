@echo off
rem Zostaví TravelTracker.exe lokálne na Windows (výsledok v priečinku dist\)
python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --onefile --windowed --name TravelTracker run.py
echo.
echo Hotovo: dist\TravelTracker.exe
pause
