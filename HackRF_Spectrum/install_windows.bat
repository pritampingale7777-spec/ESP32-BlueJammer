@echo off
setlocal EnableExtensions

set "APP_NAME=HackRF_Spectrum"
set "INSTALL_DIR=%LOCALAPPDATA%\%APP_NAME%"
set "SRC_DIR=%~dp0"

echo ==========================================
echo  HackRF Full-Spectrum Scanner - Installer
echo ==========================================
echo.

rem ---- 1. Find Python 3 -------------------------------------------------
set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [!] Python 3 not found.
    echo     Install it from https://www.python.org/downloads/
    echo     and tick "Add python.exe to PATH", then run this installer again.
    goto :fail
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
if errorlevel 1 (
    echo [!] Python 3.9 or newer is required.
    goto :fail
)
%PY% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
    echo [!] Tkinter is missing.
    echo     Re-run the Python installer, choose Modify, and enable "tcl/tk and IDLE".
    goto :fail
)
echo [OK] Python found and Tkinter is available.

rem ---- 2. Copy app files --------------------------------------------------
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
copy /Y "%SRC_DIR%hackrf_spectrum.py" "%INSTALL_DIR%\" >nul
if errorlevel 1 (
    echo [!] Could not copy hackrf_spectrum.py. Keep this installer next to the .py files.
    goto :fail
)
copy /Y "%SRC_DIR%spectrum_monitor.py" "%INSTALL_DIR%\" >nul
copy /Y "%SRC_DIR%README.md" "%INSTALL_DIR%\" >nul 2>nul
echo [OK] Files installed to %INSTALL_DIR%

rem ---- 3. Launchers ------------------------------------------------------
(
    echo @echo off
    echo cd /d "%%~dp0"
    echo %PY% hackrf_spectrum.py
    echo if errorlevel 1 pause
) > "%INSTALL_DIR%\Run_Scanner.bat"

(
    echo @echo off
    echo cd /d "%%~dp0"
    echo %PY% spectrum_monitor.py --log band_log.csv
    echo pause
) > "%INSTALL_DIR%\Run_Monitor.bat"
echo [OK] Launchers created.

rem ---- 4. Desktop shortcut -------------------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\HackRF Spectrum.lnk'); $s.TargetPath = '%INSTALL_DIR%\Run_Scanner.bat'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Description = 'HackRF full-spectrum scanner'; $s.Save()"
if errorlevel 1 (
    echo [!] Could not create the desktop shortcut. You can still run "%INSTALL_DIR%\Run_Scanner.bat".
) else (
    echo [OK] Desktop shortcut created.
)

rem ---- 5. Check HackRF host tools ----------------------------------------
where hackrf_sweep >nul 2>nul
if errorlevel 1 (
    echo.
    echo [!] hackrf_sweep was NOT found on PATH. The scanner needs it.
    echo     Download the HackRF host tools from:
    echo     https://github.com/greatscottgadgets/hackrf/releases
    echo     Extract them, then add the folder that contains hackrf_sweep.exe to your PATH.
) else (
    echo [OK] hackrf_sweep found.
)

echo.
echo Installation finished. Open "HackRF Spectrum" from your desktop, or run:
echo   %INSTALL_DIR%\Run_Scanner.bat
echo.
pause
exit /b 0

:fail
echo.
echo Installation stopped. Fix the problem above and run this installer again.
pause
exit /b 1
