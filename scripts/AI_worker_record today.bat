@echo off
title AI_worker_record launcher
setlocal
cd /d "%~dp0\.."
set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" "%CD%\scripts\window_layout.py" --desktop2 --role worker --minimize-active-windows
start "" "%CD%\scripts\AI_worker_record today_core.bat" %*
"%PYTHON_EXE%" "%CD%\scripts\window_layout.py" --role worker --window-title "AI_worker_record launcher" --wait-seconds 0.8 --minimize-window
exit
