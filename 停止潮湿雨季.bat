@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Runtime missing.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m backend.app.stop_server
ping 127.0.0.1 -n 2 >nul
