@echo off
setlocal
cd /d "%~dp0\..\.."
set PYTHON_EXE=%CD%\.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python
if "%~1"=="" (
  echo Usage: dry_run_existing_excel.cmd path\to\ARM.xlsx
  exit /b 2
)
"%PYTHON_EXE%" "%CD%\scripts\arm_export_to_collection.py" --excel "%~1" --dry-run
powershell -NoProfile -Command "Start-Sleep -Seconds 10"
