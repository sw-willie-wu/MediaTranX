"""
去背服務（rembg）
"""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4
from app.services.files.file_service import FileService, get_file_service
from app.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_REMOVE_BG = "image.remove_bg"

_MODE_TO_MODEL = {
    "auto":    "u2net",
    "person":  "u2net_human_seg",
    "product": "isnet-general-use",
    "animal":  "u2net",
    "anime":   "isnet-anime",
}


class ImageRemoveBgService:
    _instance: Optional["ImageRemoveBgService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._file_service: FileService = get_file_service()
        self._task_manager: TaskManager = get_task_manager()
        self._task_manager.register_handler(TASK_TYPE_IMAGE_REMOVE_BG, self._handle_remove_bg_task)
        self._initialized = True
        logger.info("ImageRemoveBgService initialized")

    async def submit_remove_bg(
        self,
        file_id: str,
        mode: str = "auto",
        output_dir: Optional[str] = None,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if not file_info:
            raise ValueError(f"File not found: {file_id}")
        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_REMOVE_BG, {
            "file_id": file_id,
            "mode": mode,
            "output_dir": output_dir,
        })
        return task_id

    def _handle_remove_bg_task(self, params: dict, progress_callback: Callable) -> dict:
        from PIL import Image
        from rembg import remove, new_session

        file_id = params["file_id"]
        mode = params.get("mode", "auto")
        model_name = _MODE_TO_MODEL.get(mode, "u2net")

        file_info = self._file_service.get_file(file_id)

        # === GPU 排隊管線 ===
        from app.engine.ai.model_manager import get_model_manager
        manager = get_model_manager()

        with manager.gpu_session():
            progress_callback(0.1, "載入去背模型...")
            # 將 rembg 模型路徑導向 models/rembg/，統一管理
            import os
            from app.engine.paths import get_models_dir
            os.environ["U2NET_HOME"] = str(get_models_dir("rembg"))
            session = new_session(model_name)

            from app.utils.gif_utils import animation_format, process_gif_frames, save_animated, animation_ext

            with Image.open(file_info.file_path) as raw:
                anim_fmt = animation_format(raw)
                if anim_fmt:
                    def _remove_frame(frame, idx, total):
                        progress_callback(0.4 + idx / total * 0.5, f"去除背景中 ({idx + 1}/{total})...")
                        return remove(frame, session=session)
                    result_frames = process_gif_frames(raw, _remove_frame)
                else:
                    img = raw.copy()

            output_file_id = str(uuid4())
            output_path = self._generate_output_path(file_info, params.get("output_dir"))

            progress_callback(0.9, "儲存結果...")
            if anim_fmt:
                output_path = output_path.with_suffix(animation_ext(anim_fmt))
                save_animated(result_frames, output_path, anim_fmt)
            else:
                result_img = remove(img, session=session)
                result_img.save(output_path, "PNG")

        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
        }

    def _generate_output_path(self, file_info, custom_dir) -> Path:
        target_dir = Path(custom_dir) if custom_dir else self._file_service.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / f"{Path(file_info.original_filename).stem}_nobg_{uuid4().hex[:8]}.png"


_image_remove_bg_service: Optional[ImageRemoveBgService] = None


def get_image_remove_bg_service() -> ImageRemoveBgService:
    global _image_remove_bg_service
    if _image_remove_bg_service is None:
        _image_remove_bg_service = ImageRemoveBgService()
    return _image_remove_bg_service
