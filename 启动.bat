@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 首次启动需要安装环境，请稍候...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_local.ps1"
  exit /b
)
powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://localhost:8501'"
".venv\Scripts\python.exe" -m streamlit run "work\app.py" --server.address 0.0.0.0 --server.port 8501 --server.headless true
if errorlevel 1 pause