"""
音源分離服務
使用 Demucs 將音訊分離為 6 軌（vocals, drums, bass, guitar, piano, other）
"""
import logging
import zipfile
from pathlib import Path
from typing import Callable, Optional, List
from uuid import uuid4

from app.engine.ai.audio.demucs import DemucsWrapper, get_demucs
from app.services.files.file_service import FileService, get_file_service
from app.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE_AUDIO_SEPARATE = "audio.separate"


class AudioSeparateService:
    _instance: Optional["AudioSeparateService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._demucs: DemucsWrapper = get_demucs()
        self._file_service: FileService = get_file_service()
        self._task_manager: TaskManager = get_task_manager()
        self._task_manager.register_handler(TASK_TYPE_AUDIO_SEPARATE, self._handle_task)
        self._initialized = True
        logger.info("AudioSeparateService initialized")

    def get_model_status(self, model_name: str = "htdemucs_6s") -> dict:
        return self._demucs.get_model_status(model_name)

    async def submit_separate(
        self,
        file_id: str,
        model_name: str = "htdemucs_6s",
        stems: Optional[List[str]] = None,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")
        params = {
            "file_id": file_id,
            "model_name": model_name,
            "stems": stems,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_AUDIO_SEPARATE, params)
        logger.info(f"Audio separate task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        import soundfile as sf

        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        model_name = params.get("model_name", "htdemucs_6s")
        stems = params.get("stems")

        output_file_id = str(uuid4())
        original_stem = Path(file_info.original_filename).stem
        zip_filename = f"{original_stem}_separated_{output_file_id[:8]}.zip"

        output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)

        # 暫存目錄
        temp_dir = output_dir_path / f"_demucs_temp_{output_file_id[:8]}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            progress_callback(0.0, "載入模型...")

            # 執行分離
            separated, sample_rate = self._demucs.separate(
                audio_path=str(file_info.file_path),
                variant=model_name,
                stems=stems,
                on_progress=lambda p, m: progress_callback(p * 0.9, m),
            )

            progress_callback(0.9, "寫入檔案...")

            # 儲存各 stem 為 WAV
            stem_files = []
            for stem_name, tensor in separated.items():
                wav_path = temp_dir / f"{stem_name}.wav"
                # tensor shape: (channels, samples) → transpose to (samples, channels)
                audio_data = tensor.numpy().T
                sf.write(str(wav_path), audio_data, sample_rate)
                stem_files.append(wav_path)

            # 打包 ZIP
            zip_path = output_dir_path / zip_filename
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for wav_path in stem_files:
                    zf.write(wav_path, wav_path.name)

        finally:
            # 清理暫存
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

        output_info = self._file_service.register_output(
            file_id=output_file_id, file_path=zip_path, original_filename=file_info.original_filename
        )
        progress_callback(1.0, "分離完成")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
        }


_service: Optional[AudioSeparateService] = None


def get_audio_separate_service() -> AudioSeparateService:
    global _service
    if _service is None:
        _service = AudioSeparateService()
    return _service
