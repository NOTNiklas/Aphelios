@echo off
REM Startet das APHELIOS-Backend immer über das venv, egal von wo aus
REM run.bat aufgerufen wird - verhindert das haeufigste Windows-Problem:
REM "python -m aphelios" ohne aktiviertes venv landet beim globalen Python,
REM dem die installierten Pakete (z. B. piper-tts) fehlen.
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo Kein .venv gefunden. Einmalig einrichten:
    echo   python -m venv .venv
    echo   .venv\Scripts\activate
    echo   pip install -e .
    exit /b 1
)

call ".venv\Scripts\activate.bat"
python -m aphelios
