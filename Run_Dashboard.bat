
@echo off
title Project BI - Streamlit Dashboard

cd /d "%~dp0"

if not exist "app.py" (
    echo ERROR: app.py not found in %CD%
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m streamlit run "app.py"

pause
