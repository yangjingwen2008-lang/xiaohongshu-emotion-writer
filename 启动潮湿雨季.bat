@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 缺少运行环境，请先双击“安装潮湿雨季.bat”。
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m backend.app.launch_server
if errorlevel 1 pause