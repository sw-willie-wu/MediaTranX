"""
MediaTranX 自訂例外階層
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
統一的例外類別，取代散落各處的 ValueError / RuntimeError。
Route 層可根據例外類別決定 HTTP status code。
"""


class MediaTranXError(Exception):
    """基礎例外（所有自訂例外的父類別）"""
    pass


class ModelNotFoundError(MediaTranXError):
    """模型未找到（未下載或路徑不存在）"""
    pass


class ModelLoadError(MediaTranXError):
    """模型載入失敗（權重損壞、格式錯誤、VRAM 不足）"""
    pass


class InferenceError(MediaTranXError):
    """AI 推論錯誤（模型執行中的錯誤）"""
    pass


class TaskError(MediaTranXError):
    """任務執行錯誤（一般業務邏輯錯誤）"""
    pass


class FileNotFoundError_(MediaTranXError):
    """檔案未找到（FileService 中的檔案不存在）"""
    pass


class ConfigError(MediaTranXError):
    """設定錯誤（路徑無效、設定值不合法）"""
    pass
