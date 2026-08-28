@echo off
title AI_worker_record today
setlocal
cd /d "%~dp0\.."
set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" "%CD%\scripts\window_layout.py" --role worker --console --window-title "AI_worker_record today" --wait-seconds 0.4 --minimize-active-windows
"%PYTHON_EXE%" "%CD%\scripts\crm_work_record_lookup.py" %*
set MAIN_EXIT=%ERRORLEVEL%
powershell -NoProfile -Command "Start-Sleep -Seconds 10"
exit /b %MAIN_EXIT%
