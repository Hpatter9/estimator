@echo off
setlocal
title Estimator setup
cd /d "%~dp0"
echo Setting up Estimator in %CD%
echo.

rem ---- 1. Python ----
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY goto :install_python

rem ---- 2. A private Python environment for the app, and its packages ----
echo Installing the app. The first time takes a few minutes...
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" goto :failed
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet --disable-pip-version-check
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 goto :failed

rem ---- 3. Desktop icon ----
echo Adding an Estimator icon to your desktop...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $l = $ws.CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'Estimator.lnk')); $l.TargetPath = '%~dp0Start Estimator.bat'; $l.WorkingDirectory = '%~dp0'; $l.IconLocation = '%~dp0estimator\templates\assets\icon.ico'; $l.WindowStyle = 7; $l.Save()"

echo.
echo All set. From now on, open Estimator with the icon on your desktop.
echo Starting it now...
timeout /t 3 /nobreak >nul
call "%~dp0Start Estimator.bat"
exit /b 0

:install_python
echo Python isn't installed yet. Installing it now...
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :python_manual
echo.
echo Python is installed. Close this window and double-click "Setup Estimator" again.
pause
exit /b 0

:python_manual
echo.
echo Python couldn't be installed automatically. Opening the download page:
echo install Python, tick "Add python.exe to PATH", then double-click "Setup Estimator" again.
start "" https://www.python.org/downloads/
pause
exit /b 1

:failed
echo.
echo Setup didn't finish. Check your internet connection and double-click "Setup Estimator" again.
pause
exit /b 1
