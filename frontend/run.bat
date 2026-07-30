@echo off
REM Startet den APHELIOS-Frontend-Dev-Server, immer relativ zum eigenen
REM Skript-Pfad (egal von wo aus run.bat aufgerufen wird).
cd /d "%~dp0"

if not exist "node_modules" (
    echo Kein node_modules gefunden. Einmalig einrichten:
    echo   npm install
    exit /b 1
)

npm run dev
