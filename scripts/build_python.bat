@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

echo ========================================
echo  Step 2: Compiling Backend Core (Nuitka)
echo ========================================

:: 進入 src 目錄執行 Nuitka
cd src
echo Running Nuitka compilation...
call uv run --with nuitka --with ordered-set nuitka ^
    --standalone ^
    --output-filename=core.exe ^
    --output-dir=../build/temp_nuitka ^
    --remove-output ^
    --include-module=_ssl ^
    --include-module=sqlite3 ^
    --include-data-dir=backend/static=backend/static ^
    --windows-icon-from-ico=frontend/src/assets/icon.ico ^
    --company-name="MediaTranX Team" ^
    --product-name="MediaTranX Backend" ^
    --file-version=1.0.0.0 ^
    --product-version=1.0.0.0 ^
    --file-description="MediaTranX Core Engine" ^
    --nofollow-import-to=torch ^
    --nofollow-import-to=torchvision ^
    --nofollow-import-to=transformers ^
    --nofollow-import-to=llama_cpp ^
    --nofollow-import-to=rembg ^
    --nofollow-import-to=onnxruntime ^
    backend/main.py

:: 整理目錄
cd ..
echo Organizing core engine artifacts...
if exist "build\resources\core_service" rmdir /s /q "build\resources\core_service"
if not exist "build\resources" mkdir "build\resources"

if exist "build\temp_nuitka\main.dist" (
    move "build\temp_nuitka\main.dist" "build\resources\core_service"
    echo Successfully moved core engine to build\resources\core_service
)

if exist "build\temp_nuitka" rmdir /s /q "build\temp_nuitka"

echo.
echo Backend core compilation complete.
