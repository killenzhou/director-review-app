@echo off
REM 协同审阅平台 - 便携版启动脚本 (启动便携版.bat)
REM
REM 该脚本由 build_all_in_one.bat 自动复制到 dist\协同审阅平台_完整版\ 目录
REM 在原项目目录中单独运行该脚本会找不到 llama-cpp\Qwen3-VL-8B\ 等模型，
REM 属于正常情况；请使用构建产物目录中的副本。
REM
REM 功能：
REM   1. 以后台方式启动 llama-cpp\llama-server.exe，加载 Qwen3-VL-8B 模型
REM   2. 轮询 8080 端口等待服务就绪
REM   3. 启动主程序 协同审阅平台.exe
REM   4. 主程序退出后，自动结束 llama-server.exe 进程

setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

set "ROOT=%~dp0"
set "LLAMA_DIR=%ROOT%llama-cpp"
set "MODEL_DIR=%ROOT%Qwen3-VL-8B"
set "MODEL_FILE=Qwen3VL-8B-Instruct-Q4_K_M.gguf"
set "EXE=%ROOT%协同审阅平台.exe"
set "LOG_FILE=%ROOT%qwen_server.log"

echo ============================================================>>"%LOG_FILE%"
echo [portable launcher] starting at %date% %time%>>"%LOG_FILE%"
echo [portable launcher] root: %ROOT%>>"%LOG_FILE%"

if not exist "%LLAMA_DIR%\llama-server.exe" (
    echo [ERROR] llama-server.exe not found: %LLAMA_DIR%\llama-server.exe
    echo See qwen_server.log for details.
    pause
    exit /b 1
)

if not exist "%MODEL_DIR%\%MODEL_FILE%" (
    echo [ERROR] model file not found: %MODEL_DIR%\%MODEL_FILE%
    echo See qwen_server.log for details.
    pause
    exit /b 1
)

set "MMPROJ_ARG="
for %%f in ("%MODEL_DIR%\mmproj-*.gguf" "%MODEL_DIR%\*mmproj*.gguf") do (
    if exist "%%~ff" (
        set "MMPROJ_ARG=--mmproj %%~ff"
        echo [portable launcher] mmproj: %%~nxf>>"%LOG_FILE%"
        goto found_mmproj
    )
)
:found_mmproj

echo [portable launcher] API: http://127.0.0.1:8080/v1>>"%LOG_FILE%"
echo Starting Qwen3-VL local AI server...

start "QwenServer" /min /D "%LLAMA_DIR%" "%LLAMA_DIR%\llama-server.exe" --model "%MODEL_DIR%\%MODEL_FILE%" %MMPROJ_ARG% --host 127.0.0.1 --port 8080 --ctx-size 8192 --n-gpu-layers 99 --parallel 1

echo Waiting for Qwen server to be ready (max 60s)...
set /a count=0
:wait_loop
set /a count+=1
if !count! gtr 30 goto wait_done
timeout /t 2 /nobreak >nul
netstat -an | findstr :8080 | findstr LISTENING >nul
if errorlevel 1 goto wait_loop
:wait_done
echo Qwen server is ready.

echo Starting Director Review App...
start "" /wait "%EXE%"

echo Cleaning up Qwen server...
taskkill /f /im llama-server.exe >nul 2>&1
echo [portable launcher] stopped at %date% %time%>>"%LOG_FILE%"
endlocal
exit /b 0
