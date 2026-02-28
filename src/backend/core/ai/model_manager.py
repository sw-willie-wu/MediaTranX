"""
GPU 模型記憶體管理器
智能管理多個 AI 模型的 GPU 記憶體：
- GPU 任務排隊執行，同時只有一個任務使用 GPU
- 模型用完即卸載，不佔用 VRAM
"""
import gc
import logging
import subprocess
import threading
from contextlib import contextmanager
from typing import Callable, Dict, Optional, Set

logger = logging.getLogger(__name__)

# 模型 slot 常數
SLOT_WHISPER = "whisper"
SLOT_TRANSLATEGEMMA = "translategemma"
SLOT_QWEN3 = "qwen3"
# 之後: SLOT_REALESRGAN = "realesrgan"
# 之後: SLOT_RIFE = "rife"


class ModelManager:
    """
    GPU 模型記憶體管理器（智能版）

    - acquire(slot, required_vram) 時檢查可用 VRAM
    - VRAM 足夠：直接載入，不卸載其他模型
    - VRAM 不足：按 LRU 順序卸載其他模型直到空間足夠
    - release() 標記不再使用（但保留在記憶體，直到需要騰出空間）
    """

    _instance: Optional["ModelManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._lock = threading.Lock()
        self._gpu_lock = threading.Lock()  # GPU 任務排隊鎖
        self._loaded_slots: Set[str] = set()  # 目前已載入的模型
        self._slot_order: list[str] = []  # LRU 順序（最近使用的在後面）
        self._unloaders: Dict[str, Callable[[], None]] = {}
        self._initialized = True
        logger.info("ModelManager initialized (queued GPU mode)")

    @staticmethod
    def _get_free_vram_mb() -> int:
        """透過 nvidia-smi 查詢可用 VRAM（MB），失敗回傳 0"""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return int(result.stdout.strip().split("\n")[0])
        except Exception:
            pass
        return 0

    @contextmanager
    def gpu_session(self):
        """
        排隊取得 GPU 使用權，確保同時只有一個任務管線使用 GPU。

        用法：
            with manager.gpu_session():
                # Whisper 辨識（結束後自動卸載）
                # 翻譯模型推論（結束後自動卸載）
        """
        self._gpu_lock.acquire()
        try:
            yield
        finally:
            self._gpu_lock.release()

    def register_unloader(self, slot: str, callback: Callable[[], None]) -> None:
        """
        註冊模型卸載回調

        Args:
            slot: 模型 slot 名稱
            callback: 卸載函式，呼叫後應釋放模型佔用的 GPU 記憶體
        """
        self._unloaders[slot] = callback
        logger.debug(f"Registered unloader for slot: {slot}")

    def acquire(self, slot: str, required_vram_mb: int = 0) -> None:
        """
        取得 GPU 使用權

        Args:
            slot: 要取得的模型 slot
            required_vram_mb: 預估需要的 VRAM（MB），0 表示不檢查
        """
        # 先決定要卸載哪些 slot（在 lock 內），然後在 lock 外執行卸載（避免死鎖）
        slots_to_evict: list[str] = []

        with self._lock:
            # 如果已載入，更新 LRU 順序即可
            if slot in self._loaded_slots:
                if slot in self._slot_order:
                    self._slot_order.remove(slot)
                self._slot_order.append(slot)
                logger.debug(f"Model already loaded: {slot}")
                return

            # 檢查是否需要騰出空間
            if required_vram_mb > 0:
                free_vram = self._get_free_vram_mb()
                logger.info(
                    f"VRAM check for {slot}: need {required_vram_mb}MB, "
                    f"free {free_vram}MB, loaded models: {list(self._loaded_slots)}"
                )

                # 收集需要卸載的 slot（估算）
                slots_copy = list(self._slot_order)
                for oldest_slot in slots_copy:
                    if free_vram >= required_vram_mb:
                        break
                    if oldest_slot == slot:
                        continue
                    slots_to_evict.append(oldest_slot)
                    # 粗估卸載後釋放的 VRAM（假設每個模型平均 3GB）
                    free_vram += 3000

        # 在 lock 外執行卸載（避免死鎖）
        for evict_slot in slots_to_evict:
            logger.info(f"Evicting {evict_slot} to free VRAM")
            self._evict_unlocked(evict_slot)

        # 重新取得 lock 並標記為已載入
        with self._lock:
            self._loaded_slots.add(slot)
            if slot in self._slot_order:
                self._slot_order.remove(slot)
            self._slot_order.append(slot)
            logger.info(f"GPU acquired by: {slot} (loaded: {list(self._loaded_slots)})")

    def release(self, slot: str) -> None:
        """
        釋放 GPU 使用權標記（不主動卸載模型）

        Args:
            slot: 要釋放的模型 slot
        """
        # 不做任何事，模型保留在記憶體直到需要騰出空間
        logger.debug(f"GPU released by: {slot} (model kept in memory)")

    def mark_unloaded(self, slot: str) -> None:
        """
        標記模型已卸載（由模型 wrapper 在卸載後呼叫）

        Args:
            slot: 已卸載的模型 slot
        """
        with self._lock:
            self._loaded_slots.discard(slot)
            if slot in self._slot_order:
                self._slot_order.remove(slot)
            logger.debug(f"Model marked as unloaded: {slot}")

    def _evict_unlocked(self, slot: str) -> None:
        """卸載指定 slot 的模型（不持有 lock，避免死鎖）"""
        import time

        unloader = self._unloaders.get(slot)
        if unloader:
            logger.info(f"Evicting model from memory: {slot}")
            try:
                unloader()
            except Exception as e:
                logger.warning(f"Error unloading {slot}: {e}")

        # 更新狀態（需要 lock）
        with self._lock:
            self._loaded_slots.discard(slot)
            if slot in self._slot_order:
                self._slot_order.remove(slot)

        # 注意：不呼叫 gc.collect()，因為可能觸發 CTranslate2 的 C++ 解構子 crash
        # 各模型的 unloader 應自行處理記憶體釋放（如 ctranslate2.unload_model()）
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
        except ImportError:
            pass

        # 等待 CUDA 記憶體釋放
        time.sleep(2.0)

        free_vram = self._get_free_vram_mb()
        logger.info(f"Model evicted and memory freed: {slot} (free VRAM: {free_vram}MB)")

    def _evict(self, slot: str) -> None:
        """卸載指定 slot 的模型並清理記憶體（需在 lock 內呼叫）"""
        if slot not in self._loaded_slots:
            return

        unloader = self._unloaders.get(slot)
        if unloader:
            logger.info(f"Evicting model from memory: {slot}")
            try:
                unloader()
            except Exception as e:
                logger.warning(f"Error unloading {slot}: {e}")

        # 更新狀態
        self._loaded_slots.discard(slot)
        if slot in self._slot_order:
            self._slot_order.remove(slot)

        # 清理記憶體
        gc.collect()

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.debug("CUDA cache cleared")
        except ImportError:
            pass


# 單例
_manager: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    """取得 ModelManager 單例"""
    global _manager
    if _manager is None:
        _manager = ModelManager()
    return _manager
