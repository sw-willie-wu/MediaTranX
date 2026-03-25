"""
音源分離服務
使用 Demucs 將音訊分離為 6 軌（vocals, drums, bass, guitar, piano, other）
"""
import logging
from pathlib import Path
from typing import Callable, Optional
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
        stems: Optional[list[str]] = None,
        output_format: str = "wav",
        output_dir: Optional[str] = None,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")
        params = {
            "file_id": file_id,
            "model_name": model_name,
            "stems": stems,
            "output_format": output_format,
            "output_dir": output_dir,
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

        original_stem = Path(file_info.original_filename).stem
        output_format = params.get("output_format", "wav")

        # 決定輸出目錄
        custom_output_dir = params.get("output_dir")
        if custom_output_dir:
            output_dir_path = Path(custom_output_dir)
        else:
            output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)

        progress_callback(0.0, "載入模型...")

        # === GPU 排隊管線 ===
        from app.engine.ai.model_manager import get_model_manager
        manager = get_model_manager()

        with manager.gpu_session():
            # 執行分離
            separated, sample_rate = self._demucs.separate(
                audio_path=str(file_info.file_path),
                variant=model_name,
                stems=stems,
                on_progress=lambda p, m: progress_callback(p * 0.9, m),
            )

        progress_callback(0.9, "寫入檔案...")

        # 儲存各 stem 為獨立檔案
        output_files = []
        first_file_id = None

        for stem_name, tensor in separated.items():
            filename = f"{original_stem}.{stem_name}.{output_format}"
            file_path = output_dir_path / filename
            audio_data = tensor.numpy().T

            if output_format == "mp3":
                # WAV → MP3 via ffmpeg
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    sf.write(tmp_path, audio_data, sample_rate)
                    from app.engine.ffmpeg import FFmpeg
                    ffmpeg = FFmpeg()
                    ffmpeg.convert(tmp_path, str(file_path), {"format": "mp3", "bitrate": "192k"})
                finally:
                    Path(tmp_path).unlink(missing_ok=True)
            elif output_format == "flac":
                sf.write(str(file_path), audio_data, sample_rate, format="FLAC")
            else:
                sf.write(str(file_path), audio_data, sample_rate)

            stem_file_id = str(uuid4())
            self._file_service.register_output(
                file_id=stem_file_id, file_path=file_path, original_filename=file_info.original_filename
            )
            output_files.append({
                "file_id": stem_file_id,
                "filename": filename,
                "stem": stem_name,
                "path": str(file_path),
            })
            if first_file_id is None:
                first_file_id = stem_file_id

        progress_callback(1.0, "分離完成")
        return {
            "output_file_id": first_file_id,
            "output_filename": f"{original_stem}.vocals.{output_format}",
            "output_files": output_files,
        }


_service: Optional[AudioSeparateService] = None


def get_audio_separate_service() -> AudioSeparateService:
    global _service
    if _service is None:
        _service = AudioSeparateService()
    return _service
