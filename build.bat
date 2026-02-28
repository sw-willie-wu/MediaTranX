@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo  MediaTranX Build Script
echo ========================================

REM --- Step 1: Build frontend (Vite -> backend/static) ---
echo.
echo [1/3] Building frontend...
cd src\frontend
call npx vite build
if errorlevel 1 (
    echo ERROR: Frontend build failed!
    exit /b 1
)
cd ..\..

REM --- Step 2: PyInstaller (backend -> exe) ---
echo.
echo [2/3] Building backend with PyInstaller...
.venv\Scripts\python.exe -m PyInstaller build\backend.spec --distpath build\dist --workpath build\work -y
if errorlevel 1 (
    echo ERROR: PyInstaller build failed!
    exit /b 1
)

REM --- Step 3: Electron Builder ---
echo.
echo [3/3] Building Electron installer...
cd src\frontend
call npx electron-builder --win
if errorlevel 1 (
    echo ERROR: Electron build failed!
    exit /b 1
)
cd ..\..

echo.
echo ========================================
echo  Build complete!
echo  Output: dist\
echo ========================================
