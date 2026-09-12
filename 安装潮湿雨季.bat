@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1"
set "INSTALL_RESULT=%errorlevel%"
pause
exit /b %INSTALL_RESULT%
