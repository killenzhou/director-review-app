@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

REM ============================================================================
REM  协同审阅平台 - 完整版打包脚本 (build_all_in_one.bat)
REM
REM  与原 build_portable.bat 互不影响。本脚本不修改任何已有项目文件：
REM    - main_app.py / 协同审阅平台.spec / run_dev.bat / 启动.bat / 启动Qwen.bat
REM    - build_portable.bat / settings.json
REM  原型 (run_dev.bat 启动方式) 保持不变。
REM
REM  本脚本会生成一个新目录 dist\协同审阅平台_完整版\，里面包含：
REM    - 协同审阅平台.exe (主程序)
REM    - _internal\                    (Python 运行时 + ffmpeg + Tesseract)
REM    - Qwen3-VL-8B\                  (本地 AI 视觉语言模型)
REM    - llama-cpp\                    (本地 AI 服务可执行文件)
REM    - FunASR-main\                  (FunASR 源码)
REM    - FunASR_models\                (FunASR 模型缓存)
REM    - 启动Qwen.bat                  (保留的原版 Qwen 启动脚本)
REM    - 启动便携版.bat                 (新的便携版启动器，干净启停 Qwen)
REM    - settings.json                 (干净的默认设置，不含任何用户数据)
REM    - 启动说明.txt
REM
REM  完成后该目录可整体复制到任意 Windows 10/11 x64 机器双击运行。
REM ============================================================================

set "ROOT=%~dp0"
set "PYTHON=%ROOT%director_tool_env\Scripts\python.exe"
set "SPEC=%ROOT%协同审阅平台_完整版.spec"
set "DIST=%ROOT%dist"
set "TARGET=%DIST%\协同审阅平台_完整版"

set "QWEN_SRC=G:\模型\Qwen3-VL-8B"
set "LLAMA_SRC=G:\模型\llama-cpp"
set "FUNASR_SRC=%ROOT%..\FunASR-main"
set "FUNASR_MODELS=%ROOT%FunASR_models"

set "ERROR_COUNT=0"

echo ============================================================
echo  Building Director Review App - All-in-One Portable
echo  Target: %TARGET%
echo ============================================================
echo.

REM --- pre-flight checks -----------------------------------------------------

if not exist "%PYTHON%" (
    echo [ERROR] Python venv not found: %PYTHON%
    goto :fail
)
if not exist "%SPEC%" (
    echo [ERROR] Spec file not found: %SPEC%
    goto :fail
)
if not exist "%ROOT%main_app.py" (
    echo [ERROR] main_app.py not found at project root.
    goto :fail
)
if not exist "%ROOT%external_files\ffmpeg.exe" (
    echo [ERROR] external_files\ffmpeg.exe not found at project root.
    goto :fail
)
if not exist "%ROOT%Tesseract-OCR" (
    echo [ERROR] Tesseract-OCR folder not found at project root.
    goto :fail
)
if not exist "%QWEN_SRC%\Qwen3VL-8B-Instruct-Q4_K_M.gguf" (
    echo [ERROR] Qwen model file not found at %QWEN_SRC%
    goto :fail
)
if not exist "%LLAMA_SRC%\llama-server.exe" (
    echo [ERROR] llama-server.exe not found at %LLAMA_SRC%
    goto :fail
)
if not exist "%FUNASR_SRC%\funasr" (
    echo [ERROR] FunASR source not found at %FUNASR_SRC%
    goto :fail
)
if not exist "%FUNASR_MODELS%\models" (
    echo [ERROR] FunASR_models not found at %FUNASR_MODELS%
    goto :fail
)
REM --- clean ----------------------------------------------------------------

if exist "%ROOT%build" (
    echo [clean] removing %ROOT%build
    rmdir /s /q "%ROOT%build"
)
if exist "%TARGET%" (
    echo [clean] removing %TARGET%
    rmdir /s /q "%TARGET%"
)

REM --- step 1/5: PyInstaller ------------------------------------------------

echo.
echo [1/5] Running PyInstaller with 协同审阅平台_完整版.spec ...
"%PYTHON%" -m PyInstaller "%SPEC%" --noconfirm --clean
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    goto :fail
)
if not exist "%TARGET%\协同审阅平台.exe" (
    echo [ERROR] PyInstaller did not produce %TARGET%\协同审阅平台.exe
    goto :fail
)

REM --- step 2/5: copy large models ------------------------------------------

echo.
echo [2/5] Copying large AI models to portable folder...
call :copy_dir "%QWEN_SRC%"      "%TARGET%\Qwen3-VL-8B"   || set "ERROR_COUNT=1"
if "!ERROR_COUNT!"=="1" goto :fail
call :copy_dir "%LLAMA_SRC%"     "%TARGET%\llama-cpp"     || set "ERROR_COUNT=1"
if "!ERROR_COUNT!"=="1" goto :fail

REM --- step 3/5: copy transcription assets ----------------------------------

echo.
echo [3/5] Copying FunASR assets to portable folder...
call :copy_dir "%FUNASR_SRC%"    "%TARGET%\FunASR-main"  || set "ERROR_COUNT=1"
if "!ERROR_COUNT!"=="1" goto :fail
call :copy_dir "%FUNASR_MODELS%" "%TARGET%\FunASR_models" || set "ERROR_COUNT=1"
if "!ERROR_COUNT!"=="1" goto :fail

REM --- step 4/5: launchers and settings -------------------------------------

echo.
echo [4/5] Writing portable settings, launchers and notes...
call :copy_file "%ROOT%启动Qwen.bat"   "%TARGET%\启动Qwen.bat"   || goto :fail
call :copy_file "%ROOT%启动便携版.bat"  "%TARGET%\启动便携版.bat" || goto :fail
call :write_default_settings "%TARGET%\settings.json" || goto :fail
call :write_readme            "%TARGET%\启动说明.txt"  || goto :fail

REM --- step 5/5: summary ----------------------------------------------------

echo.
echo [5/5] Done.
echo.
echo ============================================================
echo  All-in-one portable package is ready:
echo    %TARGET%
echo.
echo  Next steps:
echo    1. 打开 %TARGET%\ 目录
echo    2. 双击 协同审阅平台.exe 直接运行（推荐）
echo       - 主程序会自动启动本地 Qwen 服务
echo       - 关闭主窗口后，Qwen 仍会保留在后台；如需关闭请在
echo         任务管理器中结束 llama-server.exe
echo    3. 或双击 启动便携版.bat 干净启停 Qwen 服务
echo ============================================================
exit /b 0

:fail
echo.
echo [BUILD FAILED] Please review the error messages above.
exit /b 1

REM ============================================================================
REM  helper subroutines
REM ============================================================================

:copy_dir
REM %~1 = source, %~2 = destination
set "SRC=%~1"
set "DST=%~2"
if not exist "%SRC%" (
    echo [ERROR] Missing source folder: %SRC%
    exit /b 1
)
echo   - %SRC%  --^>  %DST%
robocopy "%SRC%" "%DST%" /E /NFL /NDL /NJH /NJS /NP /R:3 /W:5
if errorlevel 8 (
    echo [ERROR] robocopy failed for: %SRC%
    exit /b 1
)
exit /b 0

:copy_file
REM %~1 = source, %~2 = destination
set "SRC=%~1"
set "DST=%~2"
if not exist "%SRC%" (
    echo [ERROR] Missing source file: %SRC%
    exit /b 1
)
echo   - %SRC%  --^>  %DST%
copy /Y "%SRC%" "%DST%" >nul
if errorlevel 1 (
    echo [ERROR] copy failed for: %SRC%
    exit /b 1
)
exit /b 0

:write_default_settings
REM %~1 = destination file
set "DST=%~1"
>  "%DST%" echo {
>> "%DST%" echo     "project_name": "未命名项目",
>> "%DST%" echo     "producer": "",
>> "%DST%" echo     "reviewer": "",
>> "%DST%" echo     "selected_model": "funasr-paraformer-zh",
>> "%DST%" echo     "ai_provider": "local-ai",
>> "%DST%" echo     "api_key": "local",
>> "%DST%" echo     "base_url": "http://127.0.0.1:8080/v1",
>> "%DST%" echo     "model_name": "Qwen3VL-8B-Instruct-Q4_K_M.gguf",
>> "%DST%" echo     "realtime_transcribe": true,
>> "%DST%" echo     "screen_record_fps": 25,
>> "%DST%" echo     "screen_record_monitor": 0,
>> "%DST%" echo     "ffmpeg_path": "",
>> "%DST%" echo     "departments": ["动画", "灯光", "模型", "特效", "合成", "剪辑"],
>> "%DST%" echo     "audio_device_index": null,
>> "%DST%" echo     "whisper_model_path": "",
>> "%DST%" echo     "transcription_device": "auto",
>> "%DST%" echo     "transcription_compute_type": "auto",
>> "%DST%" echo     "screen_capture_backend": "gdigrab",
>> "%DST%" echo     "video_encoder": "libx264",
>> "%DST%" echo     "enable_annotation_overlay": true,
>> "%DST%" echo     "theme": "dark",
>> "%DST%" echo     "auto_start_transcription_service": true,
>> "%DST%" echo     "auto_start_ai_service": true,
>> "%DST%" echo     "table_column_widths": [],
>> "%DST%" echo     "table_column_ratios": [],
>> "%DST%" echo     "table_default_row_height": 110,
>> "%DST%" echo     "table_row_heights": {}
>> "%DST%" echo }
exit /b 0

:write_readme
REM %~1 = destination file
set "DST=%~1"
>  "%DST%" echo 协同审阅平台 - 完整版便携包
>> "%DST%" echo ============================================================
>> "%DST%" echo.
>> "%DST%" echo 本目录已包含完整运行所需的所有文件，无需任何额外环境。
>> "%DST%" echo 整目录可拷贝到任意 Windows 10/11 64-bit 电脑上运行。
>> "%DST%" echo.
>> "%DST%" echo ## 目录结构
>> "%DST%" echo   协同审阅平台.exe     主程序，双击即可启动
>> "%DST%" echo   _internal\            Python 运行时 + ffmpeg + Tesseract-OCR (请勿删除)
>> "%DST%" echo   llama-cpp\            本地 AI 服务 (llama-server.exe)
>> "%DST%" echo   Qwen3-VL-8B\          Qwen 视觉语言模型
>> "%DST%" echo   FunASR-main\          FunASR 中文语音识别源码
>> "%DST%" echo   FunASR_models\        FunASR 模型缓存 (paraformer-zh / fsmn-vad / ct-punc)
>> "%DST%" echo   启动Qwen.bat          手动启动 Qwen 的脚本 (供排错)
>> "%DST%" echo   启动便携版.bat         干净启停 Qwen 的启动器
>> "%DST%" echo   settings.json         干净默认设置 (不含任何用户数据)
>> "%DST%" echo.
>> "%DST%" echo ## 使用方法
>> "%DST%" echo.
>> "%DST%" echo 方式一 (推荐) ：双击 协同审阅平台.exe
>> "%DST%" echo   - 主程序启动约 3 秒后会自动拉起本地 Qwen 服务
>> "%DST%" echo   - 首次加载 Qwen 模型到显存约需 10-30 秒，请耐心等待
>> "%DST%" echo   - 关闭主窗口后，Qwen 服务会保留在后台
>> "%DST%" echo     如需释放显存，请在任务管理器中结束 llama-server.exe
>> "%DST%" echo.
>> "%DST%" echo 方式二 ：双击 启动便携版.bat
>> "%DST%" echo   - 启动脚本负责 Qwen 服务的启动与关闭
>> "%DST%" echo   - 关闭主窗口后，Qwen 服务也会自动结束 (释放显存)
>> "%DST%" echo.
>> "%DST%" echo ## 默认设置
>> "%DST%" echo   语音转写模型:  funasr-paraformer-zh (中文专用)
>> "%DST%" echo   本地 AI:        Qwen3-VL-8B (http://127.0.0.1:8080/v1)
>> "%DST%" echo   录屏后端:        gdigrab (Windows GDI)
>> "%DST%" echo   视频编码:        libx264 (H.264 软件编码)
>> "%DST%" echo   主题:            深色
>> "%DST%" echo.
>> "%DST%" echo ## 系统要求
>> "%DST%" echo   - Windows 10/11 64-bit
>> "%DST%" echo   - 推荐配备 NVIDIA 显卡 (GPU 加速 Qwen 推理)
>> "%DST%" echo   - 无显卡时自动使用 CPU (Qwen 首次响应约 30 秒-数分钟)
>> "%DST%" echo   - 加载 Qwen 推荐 8 GB+ 显存 (CPU 模式推荐 16 GB+ 内存)
>> "%DST%" echo.
>> "%DST%" echo ## 排错
>> "%DST%" echo   - AI 不响应:   等待 Qwen 加载完成；检查 qwen_server.log
>> "%DST%" echo   - 录屏失败:    确认 ffmpeg.exe 存在 (在 _internal\external_files\)
>> "%DST%" echo   - OCR 失败:    确认 Tesseract-OCR 存在 (在 _internal\Tesseract-OCR\)
>> "%DST%" echo   - 转写失败:    确认 FunASR_models\models 完整；首次使用需联网
exit /b 0
