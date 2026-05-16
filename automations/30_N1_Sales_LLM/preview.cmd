@echo off
setlocal
cd /d "%~dp0\..\.."
set PYTHON_EXE=%CD%\.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python
"%PYTHON_EXE%" "%CD%\scripts\N1salesLLM.py" --start-row 23 --max-rows 1 %*
powershell -NoProfile -Command "Start-Sleep -Seconds 10"
