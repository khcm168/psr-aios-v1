@echo off
setlocal
set "PROJECT_ROOT=%~dp0..\.."
if not defined PSR_GAS_ROOT set "PSR_GAS_ROOT=C:\Dev\psr-gas"
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" "%PSR_GAS_ROOT%\tools\arm_webapp_orchestrator.py" --project psr-aios-v1 --project-root "psr-aios-v1=%PROJECT_ROOT%" %*
exit /b %ERRORLEVEL%
