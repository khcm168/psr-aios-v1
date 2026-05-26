@echo off
setlocal
cd /d "%~dp0\..\.."
set PYTHON_EXE=%CD%\.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python
set DOCTOR_SCRIPT=%CD%\scripts\doctor_arm_webapps.py
if not "%ARM_DOCTOR_SCRIPT%"=="" set DOCTOR_SCRIPT=%ARM_DOCTOR_SCRIPT%
set MAIN_SCRIPT=%CD%\scripts\arm_export_to_collection.py
if not "%ARM_IMPORT_SCRIPT%"=="" set MAIN_SCRIPT=%ARM_IMPORT_SCRIPT%
set SLEEP_SECONDS=10
if not "%ARM_POST_RUN_SLEEP_SECONDS%"=="" set SLEEP_SECONDS=%ARM_POST_RUN_SLEEP_SECONDS%

"%PYTHON_EXE%" "%DOCTOR_SCRIPT%" --check import
if errorlevel 1 (
  echo [WARN] ARM import preflight failed; continuing with live ARM output.
)

"%PYTHON_EXE%" "%MAIN_SCRIPT%" %*
set MAIN_EXIT=%ERRORLEVEL%
powershell -NoProfile -Command "Start-Sleep -Seconds %SLEEP_SECONDS%"
exit /b %MAIN_EXIT%
