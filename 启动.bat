@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 首次启动需要安装环境，请稍候...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_local.ps1"
  exit /b
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_local.ps1"
if errorlevel 1 pause