"""問題回報（feedback）常數。

FORM_ID / ENTRY_IDS 在 Google 表單建立後填入真值（見 plan Task 0）。
"""

FORM_ID = "REPLACE_WITH_REAL_FORM_ID"

ENTRY_IDS = {
    "type": "entry.1000001",
    "description": "entry.1000002",
    "email": "entry.1000003",
    "app_version": "entry.1000004",
    "env_summary": "entry.1000005",
    "task_context": "entry.1000006",
    "log_tail": "entry.1000007",
}

# 前端送 key，transport 送中文 label（與 Google 表單選項逐字一致、定死）
TYPE_LABELS = {
    "bug": "問題回報",
    "feature": "功能建議",
    "other": "其他",
}

LOG_TAIL_CAP_BYTES = 40_960          # Log 尾段合計 cap（bytes）
CORE_ERROR_CAP_BYTES = 10_240        # core_error.log 優先預算（bytes）
SECTION_ASSEMBLY_CHAR_CAP = 8_000    # env_summary / task_context 組裝 cap（字元）
POST_SECTION_CHAR_LIMIT = 50_000     # POST 防禦性驗證：每節上限（字元，Sheet 單格上限）
PREFILL_URL_CAP_BYTES = 6_144        # 降級預填連結總長 cap
FORM_TIMEOUT_S = 15
EMPTY_SECTION = "(無)"


def form_response_url() -> str:
    return f"https://docs.google.com/forms/d/e/{FORM_ID}/formResponse"


def viewform_url() -> str:
    return f"https://docs.google.com/forms/d/e/{FORM_ID}/viewform"
