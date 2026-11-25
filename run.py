"""Spúšťací súbor pre PyInstaller (TravelTracker.exe)."""
import sys

from travel_tracker.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
