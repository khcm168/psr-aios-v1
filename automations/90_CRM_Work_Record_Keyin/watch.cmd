@echo off
setlocal
cd /d "%~dp0\..\.."
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" "%CD%\scripts\crm_work_record_trigger.py" %*
pause
