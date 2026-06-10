@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

set "ROOT=%~dp0"
set "LLAMA_DIR=%ROOT%llama-cpp"
set "MODEL_DIR=%ROOT%Qwen3-VL-8B"
set "MODEL_FILE=Qwen3VL-8B-Instruct-Q4_K_M.gguf"
set "LOG_FILE=%ROOT%qwen_server.log"

echo ============================================================>>"%LOG_FILE%"
echo Starting Qwen3-VL local AI server at %date% %time%>>"%LOG_FILE%"
echo Root: %ROOT%>>"%LOG_FILE%"

if not exist "%LLAMA_DIR%\llama-server.exe" (
    echo [ERROR] llama-server.exe not found: %LLAMA_DIR%\llama-server.exe>>"%LOG_FILE%"
    echo Qwen startup failed. See qwen_server.log
    exit /b 1
)

if not exist "%MODEL_DIR%\%MODEL_FILE%" (
    echo [ERROR] model not found: %MODEL_DIR%\%MODEL_FILE%>>"%LOG_FILE%"
    echo Qwen startup failed. See qwen_server.log
    exit /b 1
)

set "MMPROJ_ARG="
for %%f in ("%MODEL_DIR%\mmproj-*.gguf" "%MODEL_DIR%\*mmproj*.gguf") do (
    if exist "%%~ff" (
        set "MMPROJ_ARG=--mmproj ..\Qwen3-VL-8B\%%~nxf"
        echo [Vision] Found mmproj: %%~nxf>>"%LOG_FILE%"
        goto found_mmproj
    )
)
:found_mmproj

cd /d "%LLAMA_DIR%"
echo API: http://127.0.0.1:8080/v1>>"%LOG_FILE%"
echo Command: llama-server.exe --model ..\Qwen3-VL-8B\%MODEL_FILE% !MMPROJ_ARG! --host 127.0.0.1 --port 8080 --ctx-size 8192 --n-gpu-layers 99 --parallel 1>>"%LOG_FILE%"

llama-server.exe --model "..\Qwen3-VL-8B\%MODEL_FILE%" !MMPROJ_ARG! --host 127.0.0.1 --port 8080 --ctx-size 8192 --n-gpu-layers 99 --parallel 1 >>"%LOG_FILE%" 2>&1

echo Qwen server stopped at %date% %time%>>"%LOG_FILE%"
exit /b %ERRORLEVEL%
