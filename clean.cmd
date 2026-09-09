@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\clean.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" if not defined CI (
  echo.
  echo Cleanup failed with exit code %EXIT_CODE%.
  pause
)
exit /b %EXIT_CODE%
