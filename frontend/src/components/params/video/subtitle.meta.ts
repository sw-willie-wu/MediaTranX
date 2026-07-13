/**
 * video.subtitle 參數 META（統一參數元件 spec §4；批 2 Task 2.5——例外殼工具：SubtitlePanel.vue
 * 不刪不換 ToolParamHost，本 META 只餵 SubtitleParams.vue（工具頁殼與 pipeline dispatcher 共用）
 * 與 pipeline registry 組裝式；agent 曝光沿殼自建的舊 4 欄清單，不經本檔 schema 合成）。
 * schema 準繩＝後端 SubtitleGenerateRequest（backend/app/api/routes/video/subtitle.py）全集
 * （file_id/suppress_results 除外）＝20 欄，含 glossary（dict——v1 排除已解禁，批 2 Task 2.5 加回）。
 *
 * 後端欄位核對表：
 * | 後端欄位                   | 型別                     | 後端 default   | schema 對應                                    |
 * |-----------------------------|-------------------------|---------------|--------------------------------------------------|
 * | source_language              | Optional[str]           | None          | string（頂層——舊 panel top-level select）        |
 * | model_size                   | str                     | 'medium'      | enum WHISPER_SIZES, default 'medium'（頂層）      |
 * | output_format                | str                     | 'srt'         | enum [srt/vtt], default 'srt'（頂層）             |
 * | target_language               | Optional[str]           | None          | string（頂層；兼「翻譯啟用」gate——見下方註解）    |
 * | translate_model_family        | str                     | 'gemma4'      | string, default 'gemma4'（advanced——動態模型系）  |
 * | translate_model_size          | str                     | '4b'          | string, default '4b'（advanced）                 |
 * | translate_quantization        | Optional[str]           | None          | string（advanced）                               |
 * | translate_remote              | bool                    | False         | boolean, default false（advanced）               |
 * | translate_provider            | Optional[str]           | None          | string（advanced）                               |
 * | translate_conn_id             | Optional[int]           | None          | number（advanced）                               |
 * | translate_remote_model        | Optional[str]           | None          | string（advanced）                               |
 * | keep_names                    | bool                    | True          | boolean, default true（頂層——舊 TranslationOptionsPanel 非 SettingsCollapsible） |
 * | translate_style               | str                     | 'colloquial'  | enum TRANSLATE_STYLES, default 'colloquial'（頂層）|
 * | glossary                      | Optional[dict[str,str]] | None          | dict（頂層；無 default）                          |
 * | word_timestamps                | bool                   | False         | boolean, default false（advanced）               |
 * | condition_on_previous_text     | bool                   | True          | boolean, default true（advanced）                |
 * | min_silence_duration_ms        | int (ge100,le2000)     | 200           | number min100 max2000 step50, default200（advanced）|
 * | vad_threshold                  | float (ge0.1,le0.9)    | 0.3           | number min0.1 max0.9 step0.05, default0.3（advanced）|
 * | align                          | bool                   | False         | boolean, default false（advanced）               |
 * | vocal_separation               | bool                   | False         | boolean, default false（advanced）               |
 *
 * 佈局鐵則核對（逐欄照搬舊 SubtitlePanel.vue）：source_language/model_size/output_format 三個
 * top-level form-group；TranslationOptionsPanel（target_language/keep_names/translate_style/
 * glossary 頂層語意，translate_model_* 六欄動態模型系另標 advanced，沿 translate.meta/summary.meta
 * 既有慣例——「動態模型系欄位標 advanced」，registry.ts 檔頭規則）在舊 panel 是 top-level（非
 * SettingsCollapsible）；vocal_separation + WhisperAdvancedSettings 五欄在舊 panel 的
 * SettingsCollapsible 進階區——advanced。
 *
 * 翻譯「啟用」gate：**不新增 enable_translation 欄位**——params 恆存後端詞彙,以 target_language
 * 是否非空字串代表「翻譯已啟用」（鏡射舊 submitGenerate 的
 * `translationOptions.value?.enableTranslation && translationOptions.value.targetLanguage` 雙重
 * 判斷,因為老 UI 開關與目標語言是分開的兩個狀態,但語意上「開了翻譯又清空目標語言」等同「未翻譯」,
 * 故收斂成單一 target_language 判準)。buildSubmit() 在 gate 關閉時剔除全部 translate_*／
 * keep_names／translate_style／glossary 欄位,鏡射舊 body 組裝的 if 區塊。
 */
import type { ToolParamMeta } from '../types'

export const WHISPER_SIZES = ['tiny', 'base', 'small', 'medium', 'large-v3'] as const
export const TRANSLATE_STYLES = ['colloquial', 'formal', 'literal'] as const

/** 翻譯 composite（'translate_model'）覆蓋的七個後端欄位 */
export const TRANSLATE_FIELDS = [
  'translate_model_family', 'translate_model_size', 'translate_quantization',
  'translate_remote', 'translate_provider', 'translate_conn_id', 'translate_remote_model',
] as const

export const META: ToolParamMeta = {
  toolKey: 'video.subtitle',
  apiPath: '/video/subtitle/generate',
  labelKey: 'video.subtitle.task_label',
  // 沿舊三處三名之一（frontend taskStore.addTask 的手寫字面值)——registry.ts 檔頭已註記
  // toolKey('video.subtitle')≠後端 task_type('video.subtitle_generate')≠此值,三者故意不統一
  // (地面實況核實,批 2 Task 2.5 brief)。SubtitlePanel.vue 的殼職責是「例外」,不經 ToolParamHost，
  // 此欄位僅為滿足 ToolParamMeta 介面(taskType 必填)與未來若有東西讀 META.taskType 時的一致性,
  // 目前無人消費(shell 自己 literal 'subtitle/generate',與此值相同、非透過本欄位)。
  taskType: 'subtitle/generate',
  schema: [
    // ── 頂層：source_language/model_size/output_format（舊 panel top-level） ──────────
    { name: 'source_language', type: 'string' },
    { name: 'model_size', type: 'enum', options: [...WHISPER_SIZES], default: 'medium' },
    { name: 'output_format', type: 'enum', options: ['srt', 'vtt'], default: 'srt' },
    // ── 頂層：翻譯主欄位（舊 TranslationOptionsPanel 非 SettingsCollapsible） ──────────
    { name: 'target_language', type: 'string' },
    { name: 'keep_names', type: 'boolean', default: true },
    { name: 'translate_style', type: 'enum', options: [...TRANSLATE_STYLES], default: 'colloquial' },
    { name: 'glossary', type: 'dict' },
    // ── advanced：翻譯模型（動態模型系,沿 translate.meta/summary.meta 慣例） ──────────
    { name: 'translate_model_family', type: 'string', default: 'gemma4', advanced: true },
    { name: 'translate_model_size', type: 'string', default: '4b', advanced: true },
    { name: 'translate_quantization', type: 'string', advanced: true },
    { name: 'translate_remote', type: 'boolean', default: false, advanced: true },
    { name: 'translate_provider', type: 'string', advanced: true },
    { name: 'translate_conn_id', type: 'number', advanced: true },
    { name: 'translate_remote_model', type: 'string', advanced: true },
    // ── advanced：Whisper 進階（WhisperAdvancedSettings 五欄）+ vocal_separation ──────
    { name: 'word_timestamps', type: 'boolean', default: false, advanced: true },
    { name: 'condition_on_previous_text', type: 'boolean', default: true, advanced: true },
    { name: 'min_silence_duration_ms', type: 'number', min: 100, max: 2000, step: 50, default: 200, advanced: true },
    { name: 'vad_threshold', type: 'number', min: 0.1, max: 0.9, step: 0.05, default: 0.3, advanced: true },
    { name: 'align', type: 'boolean', default: false, advanced: true },
    { name: 'vocal_separation', type: 'boolean', default: false, advanced: true },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  /**
   * 工具頁殼分流用（沿舊 submitGenerate 的 if 區塊,gate=target_language 非空字串）。
   * payload 不含 file_id（殼 apiFetch 前自行注入,同 host 慣例）。
   * translate_quantization 僅在有值時才送（空字串視同未指定,不殘留 ''——與舊 body 逐字元
   * 相容性的唯一已知偏差,見 task report「quant 空字串」說明；isModelInstalled 對
   * quantization undefined/'' 皆視為萬用,不影響模型 guard 邏輯)。
   */
  buildSubmit(params) {
    const payload: Record<string, unknown> = {}
    if (params.source_language) payload.source_language = params.source_language
    payload.model_size = params.model_size ?? 'medium'
    payload.output_format = params.output_format ?? 'srt'
    payload.vocal_separation = params.vocal_separation === true
    payload.word_timestamps = params.word_timestamps === true
    payload.align = params.align === true
    payload.condition_on_previous_text = params.condition_on_previous_text !== false
    payload.min_silence_duration_ms = params.min_silence_duration_ms ?? 200
    payload.vad_threshold = params.vad_threshold ?? 0.3

    const targetLanguage = params.target_language
    const translateEnabled = typeof targetLanguage === 'string' && targetLanguage !== ''
    if (translateEnabled) {
      payload.target_language = targetLanguage
      if (params.translate_remote === true) {
        payload.translate_remote = true
        payload.translate_provider = params.translate_provider
        payload.translate_conn_id = params.translate_conn_id
        payload.translate_remote_model = params.translate_remote_model
      } else {
        payload.translate_model_family = params.translate_model_family ?? 'gemma4'
        payload.translate_model_size = params.translate_model_size ?? '4b'
        if (params.translate_quantization) payload.translate_quantization = params.translate_quantization
      }
      payload.keep_names = params.keep_names !== false
      payload.translate_style = params.translate_style ?? 'colloquial'
      const glossary = params.glossary
      if (glossary && typeof glossary === 'object' && Object.keys(glossary as object).length > 0) {
        payload.glossary = glossary
      }
    }

    return {
      apiPath: META.apiPath,
      payload,
      taskType: META.taskType,
      labelKey: translateEnabled ? 'video.subtitle.task_label_with_translate' : 'video.subtitle.task_label',
    }
  },
  /**
   * 複數模型需求（沿舊 SubtitlePanel.submitGenerate 四道 guard 依序——whisper → demucs(若
   * vocal_separation) → align(若 align) → translate(若 target_language 有值且非 remote)）。
   * remote 翻譯不建 requirement（雲端服務,舊碼視為恆 ready，同 summary.meta llm_remote 慣例）。
   */
  modelRequirements(params) {
    const reqs: Array<{ slot: string; family?: string; size?: string; quantization?: string; variant?: string; categories?: string[] }> = []
    reqs.push({ slot: 'whisper', variant: String(params.model_size ?? ''), categories: ['stt'] })
    if (params.vocal_separation === true) {
      reqs.push({ slot: 'separate', variant: 'htdemucs_6s', family: 'demucs', categories: ['separate'] })
    }
    if (params.align === true) {
      reqs.push({ slot: 'align', categories: ['alignment'] })
    }
    const targetLanguage = params.target_language
    const translateEnabled = typeof targetLanguage === 'string' && targetLanguage !== ''
    if (translateEnabled && params.translate_remote !== true) {
      // M2 修復：family/size 缺省時補跟 buildSubmit 一致的 fallback（'gemma4'/'4b'）,避免
      // modelRequirements 與實際送出的 payload 對「後端 default 是什麼」認知不一致。
      const req: { slot: string; family?: string; size?: string; quantization?: string } = {
        slot: 'translate',
        family: (params.translate_model_family as string | undefined) ?? 'gemma4',
        size: (params.translate_model_size as string | undefined) ?? '4b',
      }
      if (params.translate_quantization) req.quantization = params.translate_quantization as string
      reqs.push(req)
    }
    return reqs
  },
  // 舊 VideoView.handleMultiExecute 無 'subtitle' case（SubtitlePanel 硬編 isMultiSelect() 恆
  // false,見殼 agentSchema）——但 M16 註記是 agent 面板不支援多選,ToolParamMeta.multiSelect
  // 本欄實際上不被殼讀取(殼不經 ToolParamHost);False 對齊殼的既有語意,避免誤導未來讀者。
  multiSelect: false,
  persistedModelFields: ['model_size', ...TRANSLATE_FIELDS],
}

/**
 * 翻譯模型 token encode/decode（'translate_' 前綴七欄；含 quantization,格式與
 * TranslationOptionsPanel.selectedTranslateModel 的既有 token 慣例一致——local:
 * 'family:size:quantization'、remote: 'remote:provider:connId:modelId'）。
 * 與 summary.meta 的 encodeModelToken/decodeModelToken（無 quant,llm/vlm 前綴）不同構,
 * 故獨立實作,不共用（brief 設計定案 1 明文要求）。
 */
export function encodeTranslateToken(params: Record<string, unknown>): string {
  if (params.translate_remote === true) {
    const provider = params.translate_provider != null ? String(params.translate_provider) : ''
    const connId = params.translate_conn_id != null ? String(params.translate_conn_id) : ''
    const modelId = params.translate_remote_model != null ? String(params.translate_remote_model) : ''
    return `remote:${provider}:${connId}:${modelId}`
  }
  const family = params.translate_model_family != null ? String(params.translate_model_family) : ''
  const size = params.translate_model_size != null ? String(params.translate_model_size) : ''
  const quant = params.translate_quantization != null ? String(params.translate_quantization) : ''
  // family/size 皆空 → 回傳空字串,不回傳 '::'（M1 修復——避免無意義 token 被寫進
  // localStorage/usePersistedModel；quant 單獨有值但 family/size 皆空是不合法狀態,同樣視為空）。
  if (!family && !size) return ''
  return `${family}:${size}:${quant}`
}

/** decode 回傳明確覆蓋全七欄（undefined＝清除殘值),語意同 translate.meta.ts decodeModelToken。 */
export function decodeTranslateToken(token: string): Record<string, unknown> {
  if (token.startsWith('remote:')) {
    const parts = token.split(':')
    const connIdRaw = parts[2] ?? ''
    const connIdNum = Number(connIdRaw)
    return {
      translate_remote: true,
      translate_provider: parts[1] || undefined,
      translate_conn_id: connIdRaw !== '' && Number.isFinite(connIdNum) ? connIdNum : undefined,
      translate_remote_model: parts.slice(3).join(':') || undefined,
      translate_model_family: undefined,
      translate_model_size: undefined,
      translate_quantization: undefined,
    }
  }
  const [family, size, quantization] = token.split(':')
  return {
    translate_remote: false,
    translate_provider: undefined,
    translate_conn_id: undefined,
    translate_remote_model: undefined,
    translate_model_family: family || undefined,
    translate_model_size: size || undefined,
    translate_quantization: quantization || undefined,
  }
}
