@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

set "ROOT=%~dp0"
set "FULL_DIST=%ROOT%dist\协同审阅平台_便携版"
set "LIGHT_DIST=%ROOT%dist\协同审阅平台_轻量版"
set "QWEN_SRC=G:\模型\Qwen3-VL-8B"
set "LLAMA_SRC=G:\模型\llama-cpp"
set "FUNASR_SRC=%ROOT%..\FunASR-main"
set "PYTHON=%ROOT%director_tool_env\Scripts\python.exe"

echo ============================================================
echo Building Director Review App portable packages
echo ============================================================
echo.

if not exist "%PYTHON%" (
    echo [ERROR] Python venv not found: %PYTHON%
    exit /b 1
)

if exist "%ROOT%build" rmdir /s /q "%ROOT%build"
if exist "%ROOT%dist\协同审阅平台" rmdir /s /q "%ROOT%dist\协同审阅平台"
if exist "%FULL_DIST%" rmdir /s /q "%FULL_DIST%"
if exist "%LIGHT_DIST%" rmdir /s /q "%LIGHT_DIST%"

echo [1/6] Running PyInstaller...
"%PYTHON%" -m PyInstaller "%ROOT%协同审阅平台.spec" --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    exit /b 1
)

echo [2/6] Creating portable package folders...
robocopy "%ROOT%dist\协同审阅平台" "%FULL_DIST%" /E /NFL /NDL /NJH /NJS /NP
if errorlevel 8 exit /b 1
robocopy "%ROOT%dist\协同审阅平台" "%LIGHT_DIST%" /E /NFL /NDL /NJH /NJS /NP
if errorlevel 8 exit /b 1

echo [3/6] Copying shared runtime assets...
call :copy_dir "%ROOT%external_files" "%FULL_DIST%\external_files"
call :copy_dir "%ROOT%Tesseract-OCR" "%FULL_DIST%\Tesseract-OCR"
call :copy_dir "%ROOT%FunASR_models" "%FULL_DIST%\FunASR_models"
call :copy_dir "%FUNASR_SRC%" "%FULL_DIST%\FunASR-main"
call :copy_file "%ROOT%启动Qwen.bat" "%FULL_DIST%\启动Qwen.bat"
call :copy_file "%ROOT%settings.json" "%FULL_DIST%\settings.json"

call :copy_dir "%ROOT%external_files" "%LIGHT_DIST%\external_files"
call :copy_dir "%ROOT%Tesseract-OCR" "%LIGHT_DIST%\Tesseract-OCR"
call :copy_dir "%ROOT%FunASR_models" "%LIGHT_DIST%\FunASR_models"
call :copy_dir "%FUNASR_SRC%" "%LIGHT_DIST%\FunASR-main"
call :copy_file "%ROOT%settings.json" "%LIGHT_DIST%\settings.json"

echo [4/6] Copying local AI model files for full package...
call :copy_dir "%QWEN_SRC%" "%FULL_DIST%\Qwen3-VL-8B"
call :copy_dir "%LLAMA_SRC%" "%FULL_DIST%\llama-cpp"

echo [5/6] Writing startup notes...
call :write_readme "%FULL_DIST%\启动说明.txt" "完整版：包含 Qwen 本地 AI、FunASR 转写、Tesseract OCR、FFmpeg。双击 协同审阅平台.exe 使用；如需单独启动 AI，可运行 启动Qwen.bat。"
call :write_readme "%LIGHT_DIST%\启动说明.txt" "轻量版：不包含 Qwen 本地 AI。转写、OCR、录屏可用；AI 请在设置中填写远程 OpenAI 兼容服务地址。"

echo [6/6] Done.
echo Full package:  %FULL_DIST%
echo Light package: %LIGHT_DIST%
exit /b 0

:copy_dir
set "SRC=%~1"
set "DST=%~2"
if not exist "%SRC%" (
    echo [WARN] Missing folder: %SRC%
    exit /b 0
)
robocopy "%SRC%" "%DST%" /E /NFL /NDL /NJH /NJS /NP
if errorlevel 8 (
    echo [ERROR] Failed to copy folder: %SRC%
    exit /b 1
)
exit /b 0

:copy_file
set "SRC=%~1"
set "DST=%~2"
if not exist "%SRC%" (
    echo [WARN] Missing file: %SRC%
    exit /b 0
)
copy /Y "%SRC%" "%DST%" >nul
exit /b 0

:write_readme
set "DST=%~1"
set "TEXT=%~2"
>"%DST%" echo %TEXT%
>>"%DST%" echo.
>>"%DST%" echo 默认本地 AI 地址：http://127.0.0.1:8080/v1
>>"%DST%" echo 如果 AI 未启动，程序仍可进行录制、OCR 和 FunASR 转写。
exit /b 0
