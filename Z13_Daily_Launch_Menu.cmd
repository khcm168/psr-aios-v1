@echo off
setlocal
set "MENU=C:\Dev\psr-aios-v1\tools\Z13_Daily_Launch_Menu.ps1"
if not exist "%MENU%" (
  echo Missing launch menu:
  echo %MENU%
  pause
  exit /b 1
)
start "Z13 Daily Launch Menu" powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%MENU%"
