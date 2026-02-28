@echo off
echo Starting Nuitka build for core engine (Corrected Source Root Mode)...

:: 回到專案根目錄
cd ..

:: 進入 src 目錄進行編譯，這樣 backend 會被視為本地 package
cd src

:: 使用 uv run 執行 Nuitka
:: 注意：output-dir 現在相對於 src
call uv run nuitka ^
    --standalone ^
    --output-filename=core.exe ^
    --output-dir=../resources/core_engine ^
    --remove-output ^
    --include-module=_ssl ^
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

echo Nuitka build finished. core.exe is ready in resources/core_engine/main.dist/
