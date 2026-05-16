@echo off
setlocal
cd /d "%~dp0\..\.."
set PYTHON_EXE=%CD%\.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python
"%PYTHON_EXE%" "%CD%\scripts\arm_export_to_collection.py" %*
powershell -NoProfile -Command "Start-Sleep -Seconds 10"
