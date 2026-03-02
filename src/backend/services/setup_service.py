"""
系統安裝與環境 Service (REFACTOR V4)
負責 AI 環境的初始化、硬體診斷與 uv 同步，以及工具/模型下載。
"""
import os
import sys
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Callable, Optional

from backend.core.paths import get_base_data_dir, get_models_dir
from backend.core.device import get_device_info, select_torch_index
from backend.workers.progress_tracker import get_progress_tracker

logger = logging.getLogger(__name__)


class SetupService:
    """
    環境設置單例
    """
    _instance: Optional["SetupService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._setup_lock = asyncio.Lock()
        self._initialized = True

        # 向 TaskManager 註冊模型下載 handler
        from backend.workers.task_manager import get_task_manager
        get_task_manager().register_handler("setup.model_download", self._handle_model_download)
        logger.info("SetupService initialized, registered setup.model_download handler")

    async def get_system_status(self) -> dict:
        """取得詳細系統與環境狀態"""
        from backend.core.ai.model_manager import get_model_manager

        device = get_device_info()
        manager = get_model_manager()

        torch_idx = select_torch_index()
        return {
            "device": device,
            "ai_env_ready": manager.is_ai_env_ready(),
            "llama_ready": manager.is_llama_ready(),
            "base_dir": str(get_base_data_dir()),
            "python_version": sys.version.split()[0],
            "torch_index": torch_idx,
        }

    async def initialize_ai_env(self, task_id: str):
        """
        透過 uv 安裝 AI 運行環境：
          GPU 模式（3 步）：
            Step 1: uv sync --extra ai --no-dev --no-install-package torch torchvision llama-cpp-python
            Step 2: uv pip install --no-deps --index-url <pytorch_whl> torch torchvision
            Step 3: uv pip install --no-deps --index-url <llama_whl> llama-cpp-python
          CPU 模式（1 步）：
            Step 1: uv sync --extra ai --no-dev  （全部從 PyPI 安裝）
        """
        async with self._setup_lock:
            tracker = get_progress_tracker()
            await tracker.emit(task_id, 0.05, "開始診斷硬體環境...", stage="processing")

            app_root = Path(sys.executable).parent.parent.parent if getattr(sys, 'frozen', False) else Path(__file__).parent.parent.parent.parent
            uv_exe = app_root / "resources" / "uv.exe" if getattr(sys, 'frozen', False) else "uv"
            cwd = str(app_root) if not getattr(sys, 'frozen', False) else str(app_root / "resources")

            device = get_device_info()
            torch_variant = select_torch_index()
            index_url = f"https://download.pytorch.org/whl/{torch_variant}"

            driver_info = f"驅動 {device['driver_version']}" if device.get("driver_version") else "無 GPU"
            await tracker.emit(task_id, 0.1, f"偵測到 {driver_info}，選擇 Torch {torch_variant.upper()}，開始安裝...", stage="processing")

            try:
                env = os.environ.copy()
                env["UV_PROJECT_ENVIRONMENT"] = str(get_base_data_dir() / ".venv")
                env["UV_DATA_DIR"] = str(get_base_data_dir() / "uv_data")
                venv_python = get_base_data_dir() / ".venv" / "Scripts" / "python.exe"

                async def run_uv(cmd: list, progress: float) -> int:
                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=env,
                        cwd=cwd,
                    )

                    async def log_stream(stream, label):
                        while True:
                            line = await stream.readline()
                            if not line:
                                break
                            msg = line.decode('utf-8', errors='replace').strip()
                            if msg:
                                logger.info(f"[uv-{label}] {msg}")
                                await tracker.emit(task_id, progress, f"UV: {msg}", stage="processing")

                    await asyncio.gather(
                        log_stream(process.stdout, "out"),
                        log_stream(process.stderr, "err"),
                    )
                    return await process.wait()

                has_gpu = torch_variant != "cpu"

                if has_gpu:
                    # ── GPU 模式：3 步，torch / llama-cpp-python 直接裝 CUDA 版，不繞 CPU ──
                    # Step 1: 安裝其餘所有套件，排除 torch / torchvision / llama-cpp-python
                    await tracker.emit(task_id, 0.1, "安裝基礎 AI 套件中（Step 1/3）...", stage="processing")
                    rc = await run_uv([
                        str(uv_exe), "sync", "--extra", "ai", "--no-dev",
                        "--no-install-package", "torch",
                        "--no-install-package", "torchvision",
                        "--no-install-package", "llama-cpp-python",
                    ], 0.3)
                    if rc != 0:
                        await tracker.emit(task_id, 1.0, f"安裝失敗 (Code {rc})，請查看日誌。", stage="error")
                        return

                    # Step 2: 直接安裝 CUDA Torch
                    await tracker.emit(task_id, 0.4, f"安裝 CUDA Torch ({torch_variant.upper()})（Step 2/3）...", stage="processing")
                    rc = await run_uv([
                        str(uv_exe), "pip", "install",
                        "--python", str(venv_python),
                        "--no-deps",
                        "--index-url", index_url,
                        "torch", "torchvision",
                    ], 0.7)
                    if rc != 0:
                        await tracker.emit(task_id, 1.0, f"CUDA Torch 安裝失敗 (Code {rc})，請查看日誌。", stage="error")
                        return

                    # Step 3: 直接安裝 CUDA llama-cpp-python（支援 Qwen3）
                    # abetlen 官方 index 的 Windows wheel 最高只有 0.3.4，不支援 Qwen3 架構。
                    # Windows 改用社群預編譯 wheel (0.3.9 + CUDA 12.4 + Qwen3)。
                    # 注意：該 wheel 檔名非標準格式，需下載後重命名才能讓 uv/pip 接受。
                    import platform as _platform
                    if _platform.system() == "Windows":
                        qwen3_whl_url = (
                            "https://github.com/boneylizard/llama-cpp-python-cu128-gemma3/"
                            "releases/download/v0.3.9%2Bcuda124-cp312-qwen3/"
                            "llama_cpp_python-0.3.9-cp312-cp312-win_amd64-qwen3_cuda124.whl"
                        )
                        await tracker.emit(task_id, 0.75, "下載 llama-cpp-python（支援 Qwen3）（Step 3/3）...", stage="processing")
                        local_whl = await asyncio.get_running_loop().run_in_executor(
                            None, self._download_llama_wheel, qwen3_whl_url, task_id
                        )
                        if local_whl:
                            rc = await run_uv([
                                str(uv_exe), "pip", "install",
                                "--python", str(venv_python),
                                "--no-deps",
                                local_whl,
                            ], 0.9)
                            # 清理暫存檔
                            try:
                                Path(local_whl).unlink(missing_ok=True)
                            except Exception:
                                pass
                        else:
                            rc = 1
                    else:
                        llama_index = f"https://abetlen.github.io/llama-cpp-python/whl/{torch_variant}"
                        await tracker.emit(task_id, 0.75, f"安裝 CUDA llama-cpp-python ({torch_variant.upper()})（Step 3/3）...", stage="processing")
                        rc = await run_uv([
                            str(uv_exe), "pip", "install",
                            "--python", str(venv_python),
                            "--no-deps",
                            "--index-url", llama_index,
                            "llama-cpp-python",
                        ], 0.9)
                    if rc != 0:
                        # llama CUDA 版失敗不中止，後續可手動重裝
                        logger.warning(f"CUDA llama-cpp-python 安裝失敗 (Code {rc})，請查看日誌。")

                else:
                    # ── CPU 模式：1 步，全部從 PyPI 安裝 ──
                    await tracker.emit(task_id, 0.15, "安裝 AI 套件中（Step 1/1）...", stage="processing")
                    rc = await run_uv([str(uv_exe), "sync", "--extra", "ai", "--no-dev"], 0.9)
                    if rc != 0:
                        await tracker.emit(task_id, 1.0, f"安裝失敗 (Code {rc})，請查看日誌。", stage="error")
                        return

                # 清除裝置偵測快取，讓下次 /api/device 重新偵測 CUDA
                from backend.core.device import refresh_device_cache
                refresh_device_cache()

                # 安裝完成後，將 .venv site-packages 注入目前執行中的 sys.path
                # 讓同一個 session 內的 import llama_cpp / import torch 立即生效
                import sys as _sys
                venv_site = str(get_base_data_dir() / ".venv" / "Lib" / "site-packages")
                if venv_site not in _sys.path:
                    _sys.path.append(venv_site)
                torch_lib = str(get_base_data_dir() / ".venv" / "Lib" / "site-packages" / "torch" / "lib")
                import os as _os
                if _os.path.isdir(torch_lib) and hasattr(_os, 'add_dll_directory'):
                    try: _os.add_dll_directory(torch_lib)
                    except Exception: pass

                await tracker.emit(task_id, 1.0, "AI 環境安裝成功！請重新啟動應用程式以套用變更。", stage="completed")

            except Exception as e:
                logger.error(f"Setup error: {e}")
                await tracker.emit(task_id, 1.0, f"系統錯誤: {str(e)}", stage="error")

    def _download_llama_wheel(self, url: str, task_id: str) -> str | None:
        """
        下載 llama-cpp-python wheel 到臨時目錄，重命名為標準格式（去除非標準後綴），
        回傳本地路徑供 uv pip install 使用。失敗時回傳 None。
        """
        import requests, tempfile
        try:
            resp = requests.get(url, stream=True, timeout=60, allow_redirects=True)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            chunk_size = 4 * 1024 * 1024

            # 重命名：去除 wheel 名稱中的非標準後綴（如 -qwen3_cuda124）
            orig_filename = url.split("/")[-1]
            parts = orig_filename.rsplit(".whl", 1)[0].split("-")
            # 標準格式：name-version-pytag-abitag-platformtag（5 段）
            if len(parts) >= 6:
                # 合併多餘的 platform tag parts（如 win_amd64-qwen3_cuda124 → win_amd64）
                std_filename = "-".join(parts[:5]) + ".whl"
            else:
                std_filename = orig_filename

            tmpdir = tempfile.mkdtemp(prefix="mediatranx_llama_")
            local_path = os.path.join(tmpdir, std_filename)

            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

            logger.info(f"Downloaded llama wheel: {std_filename} ({downloaded // (1024*1024)}MB)")
            return local_path

        except Exception as e:
            logger.error(f"Failed to download llama wheel: {e}")
            return None

    # ─── 模型移除 ──────────────────────────────────────────────────────────────

    def remove_model(self, item_id: str) -> None:
        """刪除已下載的模型/工具檔案"""
        import shutil

        if item_id.startswith("whisper-"):
            size = item_id[len("whisper-"):]
            model_dir = get_models_dir("whisper") / size
            if model_dir.exists():
                shutil.rmtree(model_dir)
                logger.info(f"Removed whisper model: {size}")

        elif item_id.startswith("translategemma-"):
            parts = item_id.split("-", 2)
            size, quant = parts[1], parts[2]
            from backend.core.ai.registry import MODELS_REGISTRY, FORMAT_GGUF
            
            translategemma_config = MODELS_REGISTRY.get(FORMAT_GGUF, {}).get("translategemma", {})
            specs = translategemma_config.get("specs", {})
            variant = specs.get(size, {}).get("variants", {}).get(quant)
            
            if variant:
                p = get_models_dir("translategemma") / variant["filename"]
                if p.exists():
                    p.unlink()
                    logger.info(f"Removed translategemma model: {item_id}")

        elif item_id.startswith("qwen3-"):
            parts = item_id.split("-", 2)
            size, quant = parts[1], parts[2]
            from backend.core.ai.registry import MODELS_REGISTRY, FORMAT_GGUF
            
            qwen3_config = MODELS_REGISTRY.get(FORMAT_GGUF, {}).get("qwen3", {})
            specs = qwen3_config.get("specs", {})
            variant = specs.get(size, {}).get("variants", {}).get(quant)
            
            if variant:
                p = get_models_dir("qwen3") / variant["filename"]
                if p.exists():
                    p.unlink()
                    logger.info(f"Removed qwen3 model: {item_id}")

        else:
            # PTH 模型（upscale / face_restore）: {family}-{variant}
            from backend.core.ai.registry import MODELS_REGISTRY, FORMAT_PTH
            
            # 分解 ID: family-variant
            if '-' in item_id:
                family, variant = item_id.split('-', 1)
            else:
                # 舊格式相容，直接當作 family
                family = item_id
                variant = None
            
            pth_models = MODELS_REGISTRY.get(FORMAT_PTH, {})
            model_config = pth_models.get(family)
            
            if model_config:
                if variant:
                    # 刪除特定變體
                    variant_spec = model_config.get("variants", {}).get(variant)
                    if variant_spec:
                        from backend.core.ai.model_manager import get_model_manager
                        manager = get_model_manager()
                        model_path = manager.get_model_path(family, variant)
                        if model_path and model_path.exists():
                            model_path.unlink()
                            logger.info(f"Removed PTH model: {item_id}")
                else:
                    # 舊格式：刪除第一個變體
                    variants = model_config.get("variants", {})
                    if variants:
                        first_variant = list(variants.keys())[0]
                        from backend.core.ai.model_manager import get_model_manager
                        manager = get_model_manager()
                        model_path = manager.get_model_path(family, first_variant)
                        if model_path and model_path.exists():
                            model_path.unlink()
                            logger.info(f"Removed PTH model: {family}")

    # ─── 模型下載 Handler（同步，由 ThreadPoolExecutor 執行）──────────────────

    def _handle_model_download(self, params: dict, progress_callback: Callable) -> dict:
        """
        模型/工具下載任務處理器（同步）
        由 TaskManager 的 Executor 呼叫。
        """
        item_id = params.get("id", "")
        logger.info(f"Starting model download: {item_id}")
        progress_callback(0.05, f"準備下載 {item_id}...")

        try:
            from huggingface_hub import hf_hub_download, snapshot_download
        except ImportError:
            raise RuntimeError("huggingface_hub 未安裝，請先安裝基礎環境")

        if item_id.startswith("whisper-"):
            size = item_id[len("whisper-"):]
            self._download_whisper(size, progress_callback, snapshot_download)

        elif item_id.startswith("translategemma-"):
            # translategemma-4b-Q4_K_M → size=4b, quant=Q4_K_M
            parts = item_id.split("-", 2)
            size, quant = parts[1], parts[2]
            self._download_translate("translategemma", size, quant, progress_callback, hf_hub_download)

        elif item_id.startswith("qwen3-"):
            # qwen3-4b-Q4_K_M → size=4b, quant=Q4_K_M
            parts = item_id.split("-", 2)
            size, quant = parts[1], parts[2]
            self._download_translate("qwen3", size, quant, progress_callback, hf_hub_download)

        else:
            # PTH 模型（upscale / face_restore）
            self._download_pth_model(item_id, progress_callback, hf_hub_download)

        progress_callback(1.0, "下載完成")
        return {"status": "ok", "id": item_id}

    def _download_from_url(
        self,
        url: str,
        target_path: Path,
        progress_callback: Callable,
        base_progress: float = 0.1,
        end_progress: float = 0.95,
    ) -> None:
        """從直接 URL 下載檔案（支援 GitHub releases 等）"""
        import requests
        
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        response = requests.get(url, stream=True, allow_redirects=True, timeout=60)
        response.raise_for_status()
        
        total = int(response.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 4 * 1024 * 1024  # 4 MB
        
        with open(target_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        frac = downloaded / total
                        prog = base_progress + frac * (end_progress - base_progress)
                        mb_done = downloaded / 1024 / 1024
                        mb_total = total / 1024 / 1024
                        progress_callback(prog, f"下載中... {mb_done:.0f} / {mb_total:.0f} MB")
        
        if target_path.exists():
            size_mb = target_path.stat().st_size / 1024 / 1024
            progress_callback(end_progress, f"下載完成 ({size_mb:.1f} MB)")
    
    def _stream_download(
        self,
        repo_id: str,
        filename: str,
        target_path: Path,
        progress_callback: Callable,
        base_progress: float = 0.1,
        end_progress: float = 0.95,
    ) -> None:
        """透過 HuggingFace Hub 下載單一檔案"""
        from huggingface_hub import hf_hub_download
        import shutil
        
        progress_callback(base_progress, f"正在下載 {filename}...")
        
        # 確保目標目錄存在
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 使用 hf_hub_download 直接下載到目標目錄
        # local_dir_use_symlinks=False 確保檔案直接下載，不使用符號連結
        try:
            downloaded_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=target_path.parent,
                local_dir_use_symlinks=False,
            )
            
            # 檢查下載的檔案大小
            if target_path.exists():
                size_mb = target_path.stat().st_size / 1024 / 1024
                progress_callback(end_progress, f"下載完成 ({size_mb:.1f} MB)")
            else:
                progress_callback(end_progress, "下載完成")
        except Exception as e:
            raise RuntimeError(f"下載失敗: {str(e)}")

    def _download_whisper(self, size: str, progress_callback: Callable, snapshot_download) -> None:
        from backend.core.ai.registry import MODELS_REGISTRY, FORMAT_BIN
        
        whisper_config = MODELS_REGISTRY.get(FORMAT_BIN, {}).get("whisper", {})
        variants = whisper_config.get("variants", {})
        variant_spec = variants.get(size)
        
        if not variant_spec:
            raise ValueError(f"未知的 Whisper 模型大小: {size}")
        
        repo_id = variant_spec["repo_id"]
        local_dir = get_models_dir("whisper") / size
        local_dir.mkdir(parents=True, exist_ok=True)

        # model.bin 是最大的檔案（佔總大小 ~99%），先用 streaming 下載並回報進度
        model_bin = local_dir / "model.bin"
        if not model_bin.exists():
            progress_callback(0.1, f"下載 Whisper {size} 模型中...")
            self._stream_download(repo_id, "model.bin", model_bin, progress_callback, 0.1, 0.9)

        # 其餘設定小檔案用 snapshot_download 補齊（vocabulary.txt / tokenizer.json / config.json）
        progress_callback(0.9, "下載設定檔...")
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(local_dir),
            ignore_patterns=["*.md", "model.bin", "model.safetensors"],
        )
        progress_callback(0.95, "模型下載完成")

    def _download_translate(self, model_type: str, size: str, quant: str, progress_callback: Callable, hf_hub_download) -> None:
        from backend.core.ai.registry import MODELS_REGISTRY, FORMAT_GGUF
        
        model_config = MODELS_REGISTRY.get(FORMAT_GGUF, {}).get(model_type, {})
        specs = model_config.get("specs", {})
        variant = specs.get(size, {}).get("variants", {}).get(quant)
        
        if not variant:
            raise ValueError(f"未知的模型變體: {model_type}-{size}-{quant}")

        target_dir = get_models_dir(model_type)
        target_dir.mkdir(parents=True, exist_ok=True)

        progress_callback(0.1, f"下載 {model_type} {size} {quant} 中...")
        self._stream_download(
            repo_id=variant["repo_id"],
            filename=variant["filename"],
            target_path=target_dir / variant["filename"],
            progress_callback=progress_callback,
            base_progress=0.1,
            end_progress=0.95,
        )
        progress_callback(0.95, "模型下載完成")

    def _download_pth_model(self, model_id: str, progress_callback: Callable, hf_hub_download) -> None:
        """下載 PTH 模型（upscale / face_restore）"""
        from backend.core.ai.registry import MODELS_REGISTRY, FORMAT_PTH
        
        pth_models = MODELS_REGISTRY.get(FORMAT_PTH, {})
        
        # 智能分解 ID: 嘗試匹配所有 family（處理 real-cugan 這種多連字符的情況）
        family = None
        variant = None
        
        # 嘗試匹配最長的 family 前綴（避免 "real" 和 "real-cugan" 衝突）
        matched_families = [
            (family_name, model_id[len(family_name) + 1:])
            for family_name in pth_models.keys()
            if model_id.startswith(family_name + "-")
        ]
        
        if matched_families:
            # 選擇最長的匹配（最具體的 family）
            family, variant = max(matched_families, key=lambda x: len(x[0]))
        
        if not family or not variant:
            raise ValueError(f"無效的模型 ID 格式: {model_id}，無法匹配任何已知模型家族")
        
        model_config = pth_models.get(family)
        
        if not model_config:
            raise ValueError(f"未知的模型家族: {family}")
        
        variant_spec = model_config.get("variants", {}).get(variant)
        if not variant_spec:
            raise ValueError(f"未知的模型變體: {family}-{variant}")
        
        # 獲取 slot 來決定目錄結構
        slot = model_config.get("slot", "")
        if not slot:
            raise ValueError(f"模型 {family} 缺少 slot 配置")
        
        # 構建目標目錄：models/{slot}/
        target_dir = get_models_dir() / slot
        target_dir.mkdir(parents=True, exist_ok=True)
        
        filename = variant_spec["filename"]
        target_path = target_dir / filename
        
        # 檢查是否需要解壓縮
        needs_unzip = variant_spec.get("unzip", False)
        archive_path = variant_spec.get("archive_path", None)
        
        # 檢查是直接 URL 還是 HuggingFace repo_id
        if "url" in variant_spec:
            # 直接從 URL 下載（GitHub releases 等）
            url = variant_spec["url"]
            progress_callback(0.1, f"下載 {family} {variant} 中...")
            
            if needs_unzip:
                # 下載壓縮檔到臨時目錄
                import tempfile
                import zipfile
                import shutil
                from pathlib import Path as PathlibPath
                
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_archive = PathlibPath(temp_dir) / "archive.zip"
                    self._download_from_url(url, temp_archive, progress_callback, 0.1, 0.85)
                    
                    progress_callback(0.85, "解壓縮中...")
                    
                    # 解壓縮
                    with zipfile.ZipFile(temp_archive, 'r') as zip_ref:
                        # 如果指定了 archive_path，只提取該檔案
                        if archive_path:
                            # 列出所有文件以便調試
                            all_files = zip_ref.namelist()
                            
                            # 嘗試多種匹配方式
                            matching_files = []
                            
                            # 1. 精確匹配
                            if archive_path in all_files:
                                matching_files = [archive_path]
                            else:
                                # 2. 後綴匹配（處理目錄前綴）
                                matching_files = [
                                    name for name in all_files
                                    if name.endswith(archive_path) or name.endswith('/' + archive_path)
                                ]
                                
                                # 3. 如果還沒找到，嘗試只匹配基本文件名（不含路徑）
                                if not matching_files:
                                    target_basename = PathlibPath(archive_path).name
                                    matching_files = [
                                        name for name in all_files
                                        if PathlibPath(name).name == target_basename
                                    ]
                            
                            if not matching_files:
                                # 打印所有文件以便調試
                                files_list = "\n  ".join(all_files[:10])  # 只顯示前10個
                                raise ValueError(
                                    f"壓縮檔中找不到 {archive_path}\n"
                                    f"壓縮檔包含 {len(all_files)} 個文件，前幾個：\n  {files_list}"
                                )
                            
                            # 提取第一個匹配的檔案
                            source_file = matching_files[0]
                            temp_extract = PathlibPath(temp_dir) / "extracted"
                            zip_ref.extract(source_file, temp_extract)
                            
                            # 複製到最終位置
                            extracted_file = temp_extract / source_file
                            shutil.copy2(extracted_file, target_path)
                        else:
                            # 解壓全部到目標目錄
                            zip_ref.extractall(target_dir)
                    
                    progress_callback(0.95, "解壓縮完成")
            else:
                # 直接下載到目標路徑
                self._download_from_url(url, target_path, progress_callback, 0.1, 0.95)
        elif "repo_id" in variant_spec:
            # 從 HuggingFace 下載
            repo_id = variant_spec["repo_id"]
            progress_callback(0.1, f"下載 {family} {variant} 中...")
            self._stream_download(
                repo_id=repo_id,
                filename=filename,
                target_path=target_path,
                progress_callback=progress_callback,
                base_progress=0.1,
                end_progress=0.95,
            )
        else:
            raise ValueError(f"模型 {family}-{variant} 缺少 url 或 repo_id 配置")
        
        progress_callback(0.95, "模型下載完成")


def get_setup_service() -> SetupService:
    return SetupService()
