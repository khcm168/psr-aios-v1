@echo off
setlocal
cd /d "%~dp0\..\.."
set PYTHON_EXE=%CD%\.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python
"%PYTHON_EXE%" -c "import runpy, sys; sys.argv=['scripts/crm_work_record_trigger.py']+sys.argv[1:]; runpy.run_path('scripts/crm_work_record_trigger.py', run_name='__main__')" %*
pause
