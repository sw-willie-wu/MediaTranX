@echo off
echo ===================================================
echo   MediaTranX Electron Installer Builder
echo ===================================================
echo.

:: 回到前端目錄
cd ..\src\frontend

echo [1/3] Installing frontend dependencies...
call npm install

echo [2/3] Building frontend assets (Vite)...
call npm run build-only

echo [3/3] Packaging Electron application...
:: 這裡調用 package.json 裡的 build:electron 腳本
call npm run build:electron

echo.
echo ===================================================
echo   Done! 
echo   Your installer is ready in the 'dist' directory.
echo ===================================================
pause
