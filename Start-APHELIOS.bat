@echo off
REM Startet APHELIOS komplett: Backend + Frontend, jeweils in einem eigenen
REM Fenster (venv/node_modules werden dabei automatisch verwendet, siehe
REM backend\run.bat und frontend\run.bat), und oeffnet danach das HUD im
REM Standardbrowser. Fenster schliessen beendet den jeweiligen Server
REM einzeln - beide Fenster offen lassen, waehrend APHELIOS laeuft.
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\activate.bat" (
    echo Backend ist noch nicht eingerichtet. Siehe README.md, Abschnitt
    echo "Schnellstart" fuer die einmalige Einrichtung.
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo Frontend ist noch nicht eingerichtet. Siehe README.md, Abschnitt
    echo "Schnellstart" fuer die einmalige Einrichtung.
    pause
    exit /b 1
)

echo Starte Backend ...
start "APHELIOS Backend" cmd /k "%~dp0backend\run.bat"

echo Starte Frontend ...
start "APHELIOS Frontend" cmd /k "%~dp0frontend\run.bat"

echo Warte kurz, bis beide Server hochgefahren sind ...
timeout /t 4 /nobreak >nul

start "" "http://localhost:5173"
