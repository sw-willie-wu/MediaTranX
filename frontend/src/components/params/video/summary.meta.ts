/**
 * video.summary 參數 META（統一參數元件 spec §4；批 2 Task 2.4——批 2 最大工具，三模型
 * picker（whisper/llm/vlm）＋ host modelRequirements 複數擴充首用）。
 * schema 準繩＝後端 VideoSummaryRequest（backend/app/api/routes/video/summary.py）全集。
 *
 * 後端欄位核對表（file_id/suppress_results 除外——host 層注入/由 buildSubmit 決定，不進 schema）：
 * | 後端欄位                     | 型別            | 後端 default | schema 對應                        |
 * |------------------------------|-----------------|--------------|-------------------------------------|
 * | llm_model_family              | Optional[str]   | None         | string（無 default，advanced）      |
 * | llm_model_size                | Optional[str]   | None         | string（無 default，advanced）      |
 * | llm_remote                    | bool            | False        | boolean, default false, advanced    |
 * | llm_provider                  | Optional[str]   | None         | string（advanced）                  |
 * | llm_conn_id                   | Optional[int]   | None         | number（advanced）                  |
 * | llm_remote_model              | Optional[str]   | None         | string（advanced）                  |
 * | language                      | str             | 'zh-TW'      | string, default 'zh-TW'             |
 * | vlm_model_family              | Optional[str]   | None         | string（advanced）                  |
 * | vlm_model_size                | Optional[str]   | None         | string（advanced）                  |
 * | vlm_remote                    | bool            | False        | boolean, default false, advanced    |
 * | vlm_provider                  | Optional[str]   | None         | string（advanced）                  |
 * | vlm_conn_id                   | Optional[int]   | None         | number（advanced）                  |
 * | vlm_remote_model              | Optional[str]   | None         | string（advanced）                  |
 * | whisper_model_size             | str            | 'medium'     | enum WHISPER_SIZES, default 'medium'|
 * | vocal_separation               | bool           | False        | boolean, default false, advanced    |
 * | align                          | bool           | False        | boolean, default false, advanced    |
 * | word_timestamps                | bool           | False        | boolean, default false, advanced    |
 * | condition_on_previous_text     | bool           | True         | boolean, default true, advanced     |
 * | min_silence_duration_ms        | int            | 200          | number min100 max2000 step50, advanced（後端無 ge/le 約束——UI range 沿舊 WhisperAdvancedSettings.vue）|
 * | vad_threshold                  | float          | 0.3          | number min0.1 max0.9 step0.05, advanced（同上，後端無約束）|
 * | summary_mode                   | str            | 'bullets'    | enum [bullets/narrative], default 同上 |
 *
 * llm_model_family/llm_model_size/llm_remote/llm_provider/llm_conn_id/llm_remote_model 六欄
 * 由 SummaryParams.vue 註冊的 composite agent 欄位（'llm_model'）取代曝光給 agent；vlm_* 六欄
 * 同構由 'vlm_model' 取代；whisper_model_size 由 'whisper_model' 取代（單欄 covers，token=variant，
 * 同 InterpolateParams 的單欄 composite pattern）。schema 仍完整列出全欄——工具頁 UI／pipeline
 * 節點表單／validate 準繩不因 agent 層合成而改變。
 */
import type { ToolParamMeta } from '../types'

export const WHISPER_SIZES = ['tiny', 'base', 'small', 'medium', 'large-v3'] as const
export const SUMMARY_MODES = ['bullets', 'narrative'] as const

/** LLM/VLM composite 覆蓋的六個後端欄位（依 prefix 展開，見 encodeLlmToken/decodeLlmToken） */
export const LLM_FIELDS = [
  'llm_model_family', 'llm_model_size', 'llm_remote', 'llm_provider', 'llm_conn_id', 'llm_remote_model',
] as const
export const VLM_FIELDS = [
  'vlm_model_family', 'vlm_model_size', 'vlm_remote', 'vlm_provider', 'vlm_conn_id', 'vlm_remote_model',
] as const

export const META: ToolParamMeta = {
  toolKey: 'video.summary',
  apiPath: '/video/summary',
  labelKey: 'video.summary.task_label',
  taskType: 'video.summary',
  schema: [
    // 頂層敘位三欄（沿舊 VideoSummaryPanel UI：summary_mode/whisper picker 皆頂層；language
    // 舊 panel 無 UI，佈局鐵則新欄位進階區——但 schema 語意分組沿 registry 現狀，language 不標
    // advanced，避免與 summary_mode/whisper_model_size 分組準則不一致，UI 呈現另見 SummaryParams.vue）。
    { name: 'summary_mode', type: 'enum', options: [...SUMMARY_MODES], default: 'bullets' },
    { name: 'language', type: 'string', default: 'zh-TW' },
    { name: 'whisper_model_size', type: 'enum', options: [...WHISPER_SIZES], default: 'medium' },
    // LLM — 本地（family+size）或 remote 三元組，動態模型系（沿 registry 現狀標 advanced）
    { name: 'llm_model_family', type: 'string', advanced: true },
    { name: 'llm_model_size', type: 'string', advanced: true },
    { name: 'llm_remote', type: 'boolean', default: false, advanced: true },
    { name: 'llm_provider', type: 'string', advanced: true },
    { name: 'llm_conn_id', type: 'number', advanced: true },
    { name: 'llm_remote_model', type: 'string', advanced: true },
    // VLM — 選配
    { name: 'vlm_model_family', type: 'string', advanced: true },
    { name: 'vlm_model_size', type: 'string', advanced: true },
    { name: 'vlm_remote', type: 'boolean', default: false, advanced: true },
    { name: 'vlm_provider', type: 'string', advanced: true },
    { name: 'vlm_conn_id', type: 'number', advanced: true },
    { name: 'vlm_remote_model', type: 'string', advanced: true },
    // Whisper 進階（WhisperAdvancedSettings 五欄 + vocal_separation）
    { name: 'vocal_separation', type: 'boolean', default: false, advanced: true },
    { name: 'align', type: 'boolean', default: false, advanced: true },
    { name: 'word_timestamps', type: 'boolean', default: false, advanced: true },
    { name: 'condition_on_previous_text', type: 'boolean', default: true, advanced: true },
    { name: 'min_silence_duration_ms', type: 'number', min: 100, max: 2000, step: 50, default: 200, advanced: true },
    { name: 'vad_threshold', type: 'number', min: 0.1, max: 0.9, step: 0.05, default: 0.3, advanced: true },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  // 複數模型需求（批 2 Task 2.4 host modelRequirements 擴充首用）：沿舊 VideoSummaryPanel.preflight
  // 五道 guard 依序——Whisper → demucs(若 vocal_separation) → align(若 align) → LLM(非 remote) →
  // VLM(有值且非 remote)。host 逐一過 guard，第一個未就緒即中止（見 ToolParamHost.preflight()）。
  modelRequirements(params) {
    const reqs: Array<{ slot: string; family?: string; size?: string; quantization?: string; variant?: string; categories?: string[] }> = []
    reqs.push({ slot: 'whisper', variant: String(params.whisper_model_size ?? ''), categories: ['stt'] })
    if (params.vocal_separation === true) {
      reqs.push({ slot: 'separate', variant: 'htdemucs_6s', family: 'demucs', categories: ['separate'] })
    }
    if (params.align === true) {
      reqs.push({ slot: 'align', categories: ['alignment'] })
    }
    if (params.llm_remote !== true) {
      reqs.push({
        slot: 'llm',
        family: params.llm_model_family as string | undefined,
        size: params.llm_model_size as string | undefined,
      })
    }
    const vlmHasValue = Boolean(params.vlm_model_family) || Boolean(params.vlm_remote_model)
    if (vlmHasValue && params.vlm_remote !== true) {
      reqs.push({
        slot: 'vlm',
        family: params.vlm_model_family as string | undefined,
        size: params.vlm_model_size as string | undefined,
      })
    }
    return reqs
  },
  // 舊 VideoView.handleMultiExecute 的 'summary' case 已支援批次（submitToAll）——沿舊行為。
  multiSelect: true,
  // 舊 VideoSummaryPanel.agentSchema.execute.label 是 'panel.summary.execute'，
  // 與 labelKey('video.summary.task_label') 不同——見 ToolParamHost.vue agentSchema.execute 註解。
  agentExecuteLabel: 'panel.summary.execute',
  // 僅宣告「模型選擇」欄位（沿 translate/interpolate/enhance 既有慣例——persistedModelFields
  // 語意是 composite covers 的模型欄位集合，summary_mode 是 UI 偏好非模型選擇，不列入）。
  persistedModelFields: ['whisper_model_size', ...LLM_FIELDS, ...VLM_FIELDS],
}

/**
 * whisper/llm/vlm 三個 model picker 共用的 token encode/decode（prefix 區分 llm/vlm，whisper
 * 用純 variant token 不需此 helper，見 SummaryParams.vue）。
 *
 * local: 'family:size'（summary 無 quantization 欄位，與 translate 七欄版不同——只有兩段）；
 * remote: 'remote:provider:connId:modelId'（沿 useModelOptions.parseModelValue 慣例）。
 * 兩欄皆空（local 分支 family/size 皆未設）時回傳空字串——供 VLM 的「不使用」哨兵值對齊
 * （AppSelect 的 `{value:'', label: vlm_none}` 選項）。
 */
export function encodeModelToken(params: Record<string, unknown>, prefix: 'llm' | 'vlm'): string {
  const remote = params[`${prefix}_remote`] === true
  if (remote) {
    const provider = params[`${prefix}_provider`] != null ? String(params[`${prefix}_provider`]) : ''
    const connId = params[`${prefix}_conn_id`] != null ? String(params[`${prefix}_conn_id`]) : ''
    const modelId = params[`${prefix}_remote_model`] != null ? String(params[`${prefix}_remote_model`]) : ''
    return `remote:${provider}:${connId}:${modelId}`
  }
  const family = params[`${prefix}_model_family`] != null ? String(params[`${prefix}_model_family`]) : ''
  const size = params[`${prefix}_model_size`] != null ? String(params[`${prefix}_model_size`]) : ''
  if (!family && !size) return ''
  return `${family}:${size}`
}

/**
 * decode 回傳的 patch 明確覆蓋全六欄——local/remote 互斥分支各自把「另一側」欄位設 undefined
 * （undefined 語意同 translate.meta.ts decodeModelToken 檔頭註解：merge 時覆蓋殘值、送後端前
 * 被 JSON.stringify/normalizeParams 丟棄）。空字串 token（VLM「不使用」哨兵）落入 local 分支
 * （''.split(':') → ['']，family=''→undefined、size=undefined→undefined），六欄全清、
 * remote 明確設 false——與 encodeModelToken 的空字串編碼互為逆函式。
 */
export function decodeModelToken(token: string, prefix: 'llm' | 'vlm'): Record<string, unknown> {
  if (token.startsWith('remote:')) {
    const parts = token.split(':')
    const connIdRaw = parts[2] ?? ''
    const connIdNum = Number(connIdRaw)
    return {
      [`${prefix}_remote`]: true,
      [`${prefix}_provider`]: parts[1] || undefined,
      [`${prefix}_conn_id`]: connIdRaw !== '' && Number.isFinite(connIdNum) ? connIdNum : undefined,
      [`${prefix}_remote_model`]: parts.slice(3).join(':') || undefined,
      [`${prefix}_model_family`]: undefined,
      [`${prefix}_model_size`]: undefined,
    }
  }
  const [family, size] = token.split(':')
  return {
    [`${prefix}_remote`]: false,
    [`${prefix}_provider`]: undefined,
    [`${prefix}_conn_id`]: undefined,
    [`${prefix}_remote_model`]: undefined,
    [`${prefix}_model_family`]: family || undefined,
    [`${prefix}_model_size`]: size || undefined,
  }
}
