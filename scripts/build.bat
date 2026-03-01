@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

echo ========================================
echo  MediaTranX Professional Build System
echo ========================================

:: 1. Vue Build
call scripts\build_vue.bat
if errorlevel 1 exit /b 1

:: 2. Python Build
call scripts\build_python.bat
if errorlevel 1 exit /b 1

:: 3. Electron Build
call scripts\build_electron.bat
if errorlevel 1 exit /b 1

echo.
echo ========================================
echo  ALL STAGES COMPLETE!
echo ========================================
pause
