@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
echo [1/2] Building backend with PyInstaller...
.venv\Scripts\python.exe -m PyInstaller build\backend.spec --distpath build\dist --workpath build\work -y
if errorlevel 1 (
    echo ERROR: PyInstaller build failed!
    exit /b 1
)
echo [2/2] Building Electron installer...
cd src\frontend
call npx electron-builder --win
if errorlevel 1 (
    echo ERROR: Electron build failed!
    exit /b 1
)
cd ..\..
echo Build complete!
echo Output: dist\
