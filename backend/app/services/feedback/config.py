"""問題回報（feedback）常數。

FORM_ID / ENTRY_IDS 對應正式表單「MediaTranX 意見回報」（2026-07-06 建立，
回應連結至 Google Sheet「MediaTranX 意見回報 (回覆)」）。
"""

FORM_ID = "1FAIpQLSfASO6Yhp87CBkVd9B2IJa_Eg72L12hsPPdyphmP89LPR66tw"

ENTRY_IDS = {
    "type": "entry.715300869",
    "description": "entry.2006620054",
    "email": "entry.1611767768",
    "app_version": "entry.813553844",
    "env_summary": "entry.275414751",
    "task_context": "entry.653612363",
    "log_tail": "entry.1672329663",
}

# 前端送 key，transport 送中文 label（與 Google 表單選項逐字一致、定死）
TYPE_LABELS = {
    "bug": "問題回報",
    "feature": "功能建議",
    "other": "其他",
}

LOG_TAIL_CAP_BYTES = 40_960          # Log 尾段原始 cap（bytes；encoded 預算後通常更小）
CORE_ERROR_CAP_BYTES = 10_240        # core_error.log 優先預算（bytes）
SECTION_ASSEMBLY_CHAR_CAP = 8_000    # env_summary / task_context 組裝 cap（字元）
POST_SECTION_CHAR_LIMIT = 50_000     # POST 防禦性驗證：每節上限（字元，Sheet 單格上限）

# Google formResponse 的 POST body 上限實測 ~31KB（超過回 413，2026-07-06 對真表單
# 二分實測：30,720 OK / 32,768 413）。各自動節以 URL-encoded 後大小配預算，
# 合計 26.6KB + description + 輔助欄位 overhead，離 31K 留安全 margin。
# 截斷在「組裝端」做（維持所見即所送：預覽 = 送出）。
LOG_TAIL_ENCODED_BUDGET = 16_384     # Log 尾段 encoded 預算（保尾端＝最新行）
ENV_ENCODED_BUDGET = 4_096           # 環境摘要 encoded 預算（保頭端）
TASK_ENCODED_BUDGET = 6_144          # 任務脈絡 encoded 預算（保頭端＝task_type/error_code）
PREFILL_URL_CAP_BYTES = 6_144        # 降級預填連結總長 cap
FORM_TIMEOUT_S = 15
EMPTY_SECTION = "(無)"


def form_response_url() -> str:
    return f"https://docs.google.com/forms/d/e/{FORM_ID}/formResponse"


def viewform_url() -> str:
    return f"https://docs.google.com/forms/d/e/{FORM_ID}/viewform"
