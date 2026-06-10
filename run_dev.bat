@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

if exist "%~dp0启动Qwen.bat" (
    echo Starting Qwen backend...
    start "" /min "%ComSpec%" /c call "%~dp0启动Qwen.bat"
) else (
    echo Qwen startup script not found. Skipping backend start.
)

echo Starting Director Review App...
set "PATH=%~dp0director_tool_env\Scripts;%PATH%"
director_tool_env\Scripts\python.exe main_app.py
pause
