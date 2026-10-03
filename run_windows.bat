@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.11 -m venv .venv
  if errorlevel 1 (
    echo Please install Python 3.11 or create .venv manually.
    pause
    exit /b 1
  )
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m streamlit run object_detection_app.py
pause
