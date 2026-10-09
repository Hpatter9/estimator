@echo off
title Estimator - keep this window open while you use the app
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Estimator isn't set up yet. Double-click "Setup Estimator" first.
  pause
  exit /b 1
)

rem Already running? Just open it in the browser.
powershell -NoProfile -Command "try { (New-Object Net.Sockets.TcpClient).Connect('localhost', 8501); exit 0 } catch { exit 1 }"
if not errorlevel 1 (
  start "" http://localhost:8501
  exit /b 0
)

rem Get the latest version if this folder came from GitHub (skipped quietly when offline).
set GIT_TERMINAL_PROMPT=0
if exist ".git" where git >nul 2>nul && git pull --ff-only --quiet >nul 2>nul && ".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet --disable-pip-version-check >nul 2>nul

rem Open the browser a few seconds after the app starts.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 5; Start-Process 'http://localhost:8501'"
echo Estimator is running at http://localhost:8501
echo Close this window to stop it.
".venv\Scripts\python.exe" -m streamlit run app.py
