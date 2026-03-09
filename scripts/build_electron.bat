@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

echo ========================================
echo  Step 3: Packaging Electron Installer
echo ========================================

:: --- 原 collect_assets 邏輯整合 ---
echo [1/2] Staging resources in build directory...
if not exist "build" mkdir "build"
if not exist "build\resources" mkdir "build\resources"

:: 清理舊的輔助工具目錄
if exist "build\resources\wheels" rmdir /s /q "build\resources\wheels"
if exist "build\resources\python" rmdir /s /q "build\resources\python"

echo Collecting Manager and Configuration...
:: 複製 uv.exe
set "UV_PATH="
for /f "tokens=*" %%i in ('where uv 2^>nul') do set "UV_PATH=%%i"
if defined UV_PATH (
    copy "!UV_PATH!" "build\resources\uv.exe" /y >nul
)

:: 複製配置檔案
copy "pyproject.toml" "build\resources\pyproject.toml" /y >nul
if exist "uv.lock" copy "uv.lock" "build\resources\uv.lock" /y >nul

:: 複製 FFmpeg 二進位工具 (排除 ffplay 以節省空間)
if exist "bin\ffmpeg" (
    echo [Resources] Copying FFmpeg and FFprobe - skipping ffplay...
    if not exist "build\resources\ffmpeg" mkdir "build\resources\ffmpeg"
    copy "bin\ffmpeg\ffmpeg.exe" "build\resources\ffmpeg" /y >nul
    copy "bin\ffmpeg\ffprobe.exe" "build\resources\ffmpeg" /y >nul
)

:: --- 執行 Electron 打包 ---
echo.
echo [2/2] Running Electron Builder...
cd src\electron
call npm install
call npm run build:electron
if errorlevel 1 (
    echo ERROR: Electron packaging failed!
    exit /b 1
)
cd ..\..

echo.
echo ========================================
echo  SUCCESS: Installer is ready in 'dist'
echo ========================================
