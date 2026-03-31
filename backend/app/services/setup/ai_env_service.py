"""
AI 環境初始化服務
負責透過 uv 安裝 AI 運行環境（PyTorch + 相關套件）及下載 llama-server 二進位。
"""
import os
import sys
import json
import logging
import asyncio
import platform
import tempfile
import zipfile
import urllib.request
import urllib.error
from pathlib import Path

from app.engine.paths import get_base_data_dir, get_llama_bin_dir, _get_app_root, _is_frozen
from app.engine.device import get_device_info, select_torch_index
from app.workers.progress_tracker import get_progress_tracker

logger = logging.getLogger(__name__)


def _check_demucs_api() -> bool:
    """檢查 demucs 套件含 api 模組（GitHub 版）是否已安裝"""
    try:
        from demucs.api import Separator  # noqa: F401
        return True
    except (ImportError, ModuleNotFoundError):
        return False


def _check_torch_variant(expected_variant: str) -> bool:
    """檢查已安裝的 torch 版本是否符合預期 variant（如 cu124、cpu）"""
    try:
        import torch
        version = torch.__version__  # e.g. '2.10.0+cu124'
        plus = version.find('+')
        installed = version[plus + 1:] if plus >= 0 else ''
        if installed != expected_variant:
            return False
    except ImportError:
        return False
    return True


def _check_llama_server() -> bool:
    """檢查 llama-server 二進位是否存在"""
    import sys as _sys
    exe_name = "llama-server.exe" if _sys.platform == "win32" else "llama-server"
    return (get_llama_bin_dir() / exe_name).exists()


async def initialize_ai_env(setup_lock: asyncio.Lock, task_id: str):
    """
    透過 uv 安裝 AI 運行環境：
      Step 1: uv sync --extra ai --no-dev --no-install-package torch torchvision
      Step 2: uv pip install --no-deps --index-url <pytorch_whl> torch torchvision
      Step 3: uv pip install --no-deps --no-cache-dir git+https://github.com/facebookresearch/demucs
      Step 4: 下載 llama-server 二進位
    """
    async with setup_lock:
        tracker = get_progress_tracker()
        await tracker.emit(task_id, 0.05, "開始診斷硬體環境...", stage="processing")

        app_root = _get_app_root()
        uv_exe = app_root / "resources" / "uv.exe" if _is_frozen() else "uv"
        cwd = str(app_root / "resources") if _is_frozen() else str(app_root)
        logger.info(f"uv setup: app_root={app_root}, cwd={cwd}, uv={uv_exe}")

        device = get_device_info()
        torch_variant = select_torch_index()
        index_url = f"https://download.pytorch.org/whl/{torch_variant}"

        driver_info = f"驅動 {device['driver_version']}" if device.get("driver_version") else "無 GPU"
        await tracker.emit(task_id, 0.1, f"偵測到 {driver_info}，選擇 Torch {torch_variant.upper()}，開始安裝...", stage="processing")

        try:
            env = os.environ.copy()
            env["UV_PROJECT_ENVIRONMENT"] = str(get_base_data_dir() / ".venv")
            env["UV_DATA_DIR"] = str(get_base_data_dir() / "uv_data")
            from app.engine.paths import get_venv_python
            venv_python = get_venv_python()

            async def run_uv(cmd: list, prog_start: float, prog_end: float) -> int:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    cwd=cwd,
                )

                _prog = [prog_start]

                async def log_stream(stream, label):
                    while True:
                        line = await stream.readline()
                        if not line:
                            break
                        msg = line.decode('utf-8', errors='replace').strip()
                        if msg:
                            if label == "err":
                                logger.warning(f"[uv-err] {msg}")
                            else:
                                logger.info(f"[uv-out] {msg}")
                            # 只在 uv 安裝套件時（+ package==version）才更新前端進度
                            if msg.startswith('+'):
                                pkg = msg[1:].strip().split('==')[0]
                                # 漸近推進：每個套件吃掉剩餘距離的 12%，永不超過 prog_end
                                _prog[0] += (prog_end - _prog[0]) * 0.12
                                await tracker.emit(task_id, _prog[0], f"安裝 {pkg}...", stage="processing")

                await asyncio.gather(
                    log_stream(process.stdout, "out"),
                    log_stream(process.stderr, "err"),
                )
                return await process.wait()

            has_gpu = torch_variant != "cpu"

            # ── 檢查哪些步驟可以跳過（僅 torch / demucs-api / llama）──
            demucs_api_ok = _check_demucs_api()
            torch_ok = _check_torch_variant(torch_variant)
            llama_ok = _check_llama_server()

            if demucs_api_ok and torch_ok and llama_ok:
                # uv sync 仍然要跑（讓 uv 自己判斷是否需要更新）
                await tracker.emit(task_id, 0.1, "檢查工具執行模組（Step 1/3）...", stage="processing")
            else:
                await tracker.emit(task_id, 0.1, "安裝工具執行模組（Step 1/3）...", stage="processing")

            # Step 1a: uv sync（永遠執行，uv 自行判斷差異，已安裝時幾乎瞬間完成）
            # --inexact: 不移除 lock file 外的套件（torch/demucs 由後續步驟另裝）
            rc = await run_uv([
                str(uv_exe), "--project", cwd, "sync", "--extra", "ai", "--no-dev",
                "--inexact",
                "--no-install-package", "torch",
                "--no-install-package", "torchvision",
                "--no-install-package", "torchaudio",
            ], 0.1, 0.28)
            if rc != 0:
                await tracker.emit(task_id, 1.0, f"安裝失敗 (Code {rc})，請查看日誌。", stage="error")
                return

            # Step 1b: Demucs API（GitHub 版，需額外安裝）
            if not demucs_api_ok:
                await tracker.emit(task_id, 0.29, "安裝 Demucs API 模組...", stage="processing")
                rc = await run_uv([
                    str(uv_exe), "pip", "install",
                    "--python", str(venv_python),
                    "--no-deps", "--no-cache-dir",
                    "git+https://github.com/facebookresearch/demucs",
                ], 0.29, 0.34)
                if rc != 0:
                    await tracker.emit(task_id, 1.0, f"Demucs 安裝失敗 (Code {rc})，請查看日誌。", stage="error")
                    return

            # Step 2: PyTorch（CUDA 或 CPU）
            if not torch_ok:
                label = f"CUDA Torch ({torch_variant.upper()})" if has_gpu else "CPU Torch"
                await tracker.emit(task_id, 0.35, f"安裝 {label}（Step 2/3）...", stage="processing")
                rc = await run_uv([
                    str(uv_exe), "pip", "install",
                    "--python", str(venv_python),
                    "--no-deps",
                    "--index-url", index_url,
                    "torch", "torchvision", "torchaudio",
                ], 0.35, 0.59)
                if rc != 0:
                    await tracker.emit(task_id, 1.0, f"{label} 安裝失敗 (Code {rc})，請查看日誌。", stage="error")
                    return
            else:
                await tracker.emit(task_id, 0.59, f"Torch {torch_variant.upper()} 已安裝，跳過 Step 2/3", stage="processing")

            # Step 3: llama-server
            if not llama_ok:
                await tracker.emit(task_id, 0.6, "下載 llama-server 二進位（Step 3/3）...", stage="processing")
                llama_variant = torch_variant if has_gpu else "cpu"
                loop = asyncio.get_running_loop()
                ok = await loop.run_in_executor(
                    None, download_llama_server, llama_variant, task_id, loop, 0.6, 0.85, 1.0
                )
                if not ok:
                    logger.warning("llama-server 下載失敗，請稍後手動重試。")
            else:
                await tracker.emit(task_id, 0.95, "llama-server 已存在，跳過 Step 3/3", stage="processing")

            # 清除裝置偵測快取
            from app.engine.device import refresh_device_cache
            refresh_device_cache()

            # 將 .venv site-packages 注入 sys.path
            import sys as _sys
            from app.engine.paths import get_venv_site_packages
            venv_site = str(get_venv_site_packages())
            if venv_site not in _sys.path:
                _sys.path.append(venv_site)
            torch_lib = str(Path(venv_site) / "torch" / "lib")
            import os as _os
            if _os.path.isdir(torch_lib) and hasattr(_os, 'add_dll_directory'):
                try: _os.add_dll_directory(torch_lib)
                except Exception: pass

            await tracker.emit(task_id, 1.0, "AI 環境安裝成功！請重新啟動應用程式以套用變更。", stage="completed")

        except Exception as e:
            logger.error(f"Setup error: {e}")
            await tracker.emit(task_id, 1.0, f"系統錯誤: {str(e)}", stage="error")


def download_llama_server(
    torch_variant: str,
    task_id: str,
    loop: asyncio.AbstractEventLoop = None,
    prog_start: float = 0.75,
    prog_end: float = 0.95,
    cudart_end: float = 0.99,
) -> bool:
    """
    從 llama.cpp GitHub releases 下載 llama-server 二進位，
    解壓後放置到 bin/llama/ 目錄。失敗時回傳 False。
    """
    try:
        llama_bin = get_llama_bin_dir()
        llama_bin.mkdir(parents=True, exist_ok=True)

        system = platform.system()
        exe_name = "llama-server.exe" if system == "Windows" else "llama-server"

        # 查詢 GitHub API 取最新 release assets
        api_url = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
        req = urllib.request.Request(api_url, headers={"User-Agent": "MediaTranX/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            release = json.loads(resp.read())

        tag = release["tag_name"]
        assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
        logger.info(f"Latest llama.cpp release: {tag}, assets: {list(assets.keys())}")

        # 依平台選擇 asset
        url = None
        cudart_url = None
        if system == "Windows":
            if torch_variant != "cpu":
                for name, asset_url in assets.items():
                    if name.startswith("llama-") and "win" in name and "cuda-12.4" in name and name.endswith(".zip"):
                        url = asset_url
                        break
                if not url:
                    for name, asset_url in assets.items():
                        if name.startswith("llama-") and "win" in name and "cuda" in name and name.endswith(".zip"):
                            url = asset_url
                            break
                if url:
                    cuda_ver = None
                    for seg in url.split("/")[-1].split("-"):
                        if seg.startswith("cuda-"):
                            cuda_ver = seg
                            break
                    for name, asset_url in assets.items():
                        if name.startswith("cudart-") and "win" in name and name.endswith(".zip"):
                            if cuda_ver and cuda_ver in name:
                                cudart_url = asset_url
                                break
                    if not cudart_url:
                        for name, asset_url in assets.items():
                            if name.startswith("cudart-") and "win" in name and name.endswith(".zip"):
                                cudart_url = asset_url
                                break
            if not url:
                for name, asset_url in assets.items():
                    if "win" in name and "avx2" in name and name.endswith(".zip"):
                        url = asset_url
                        break
                if not url:
                    for name, asset_url in assets.items():
                        if "win" in name and name.endswith(".zip") and "cuda" not in name:
                            url = asset_url
                            break
        else:
            for name, asset_url in assets.items():
                if "ubuntu" in name and "x64" in name and name.endswith(".zip"):
                    url = asset_url
                    break

        if not url:
            logger.error(f"No suitable llama-server asset found in release {tag}")
            return False

        logger.info(f"Downloading llama-server from {url}")
        if cudart_url:
            logger.info(f"Will also download cudart DLLs from {cudart_url}")

        def _emit(prog: float, msg: str):
            if loop and not loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    tracker.emit(task_id, prog, msg, stage="processing"), loop
                )

        tracker = get_progress_tracker()

        with tempfile.TemporaryDirectory(prefix="mediatranx_llama_") as tmpdir:
            archive = Path(tmpdir) / url.split("/")[-1]

            req = urllib.request.urlopen(url, timeout=120)
            total = int(req.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 4 * 1024 * 1024

            with open(archive, "wb") as f:
                while True:
                    chunk = req.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        frac = downloaded / total
                        prog = prog_start + frac * (prog_end - prog_start)
                        mb_done = downloaded // (1024 * 1024)
                        mb_total = total // (1024 * 1024)
                        _emit(prog, f"下載 llama-server... {mb_done}/{mb_total} MB")

            with zipfile.ZipFile(archive, "r") as zf:
                for entry in zf.namelist():
                    basename = Path(entry).name
                    if basename == exe_name:
                        data = zf.read(entry)
                        (llama_bin / basename).write_bytes(data)
                        if system != "Windows":
                            (llama_bin / basename).chmod(0o755)
                        logger.info(f"Extracted {basename} → {llama_bin}")
                    elif system == "Windows" and basename.endswith(".dll"):
                        data = zf.read(entry)
                        (llama_bin / basename).write_bytes(data)
                        logger.info(f"Extracted DLL: {basename}")

            if cudart_url:
                cudart_archive = Path(tmpdir) / cudart_url.split("/")[-1]
                _emit(0.95, "下載 CUDA runtime DLLs...")
                with urllib.request.urlopen(cudart_url, timeout=120) as r:
                    total_c = int(r.headers.get("Content-Length", 0))
                    downloaded_c = 0
                    with open(cudart_archive, "wb") as f:
                        while True:
                            chunk = r.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded_c += len(chunk)
                            if total_c > 0:
                                frac_c = downloaded_c / total_c
                                prog_c = prog_end + frac_c * (cudart_end - prog_end)
                                mb_done_c = downloaded_c // (1024 * 1024)
                                mb_total_c = total_c // (1024 * 1024)
                                _emit(prog_c, f"下載 CUDA DLLs... {mb_done_c}/{mb_total_c} MB")
                with zipfile.ZipFile(cudart_archive, "r") as zf:
                    for entry in zf.namelist():
                        basename = Path(entry).name
                        if basename.endswith(".dll"):
                            (llama_bin / basename).write_bytes(zf.read(entry))
                            logger.info(f"Extracted cudart DLL: {basename}")

        return (llama_bin / exe_name).exists()

    except Exception as e:
        logger.error(f"Failed to download llama-server: {e}")
        return False
