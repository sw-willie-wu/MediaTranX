@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

echo ========================================
echo  Step 1: Building Frontend (Vue 3)
echo ========================================

cd src\frontend
echo Installing dependencies...
call npm install
echo Building assets...
call npx vite build
if errorlevel 1 (
    echo ERROR: Vite build failed!
    exit /b 1
)
cd ..\..

echo.
echo Frontend build complete.
