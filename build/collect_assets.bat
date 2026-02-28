@echo off
setlocal enabledelayedexpansion

echo [1/3] Cleaning up specific managed resources...
cd ..
:: 只清理我們管理的子目錄，保留 backend.exe
if not exist "resources" mkdir "resources"
if exist "resources\wheels" rmdir /s /q "resources\wheels"
if exist "resources\python" rmdir /s /q "resources\python"

echo [2/3] Collecting UV and Configuration...
:: 複製 uv.exe
where uv >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    for /f "tokens=*" %%i in ('where uv') do set UV_PATH=%%i
    copy "!UV_PATH!" "resources\uv.exe" /y >nul
)

:: 複製配置檔案
copy "pyproject.toml" "resources\pyproject.toml" /y >nul
if exist "uv.lock" copy "uv.lock" "resources\uv.lock" /y >nul

echo [3/3] Done! Assets collected.
echo NOTE: Remember to run nuitka_build.bat to ensure backend.exe is present in resources/
