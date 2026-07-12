/**
 * audio.transcribe 參數 META（統一參數元件 spec §4；批 3 Task 3.4——批 3 最大工具，三個
 * composite：whisper 單欄／translate 七欄／summarize 七欄）。
 * schema 準繩＝後端 AudioTranscribeRequest（backend/app/api/routes/audio/transcribe.py）
 * 全集（file_id/suppress_results 除外）＝29 欄。
 *
 * 後端欄位核對表：
 * | 後端欄位                   | 型別                     | 後端 default   | schema 對應                                    |
 * |-----------------------------|-------------------------|---------------|--------------------------------------------------|
 * | source_language              | Optional[str]           | None          | string（頂層——舊 panel top-level select）        |
 * | model_size                   | str                     | 'medium'      | enum WHISPER_SIZES, default 'medium'（頂層）      |
 * | output_format                | str                     | 'txt'         | enum [txt/srt], default 'txt'（頂層）             |
 * | vocal_separation              | bool                   | False         | boolean, default false（advanced——舊 SettingsCollapsible） |
 * | align                         | bool                   | False         | boolean, default false（advanced）               |
 * | translate                     | bool                   | False         | boolean, default false（頂層——**獨立 gate 欄位**，見下方註解） |
 * | target_language               | Optional[str]           | None          | string（頂層；visibleWhen translate===true）      |
 * | translate_model_family        | str                     | 'gemma4'      | string, default 'gemma4'（advanced；visibleWhen translate===true） |
 * | translate_model_size          | str                     | '4b'          | string, default '4b'（advanced；同上）            |
 * | translate_quantization        | Optional[str]           | None          | string（advanced；同上）                         |
 * | translate_remote              | bool                    | False         | boolean, default false（advanced；同上）         |
 * | translate_provider            | Optional[str]           | None          | string（advanced；同上）                         |
 * | translate_conn_id             | Optional[int]           | None          | number（advanced；同上）                         |
 * | translate_remote_model        | Optional[str]           | None          | string（advanced；同上）                         |
 * | summarize                     | bool                    | False         | boolean, default false（頂層——**第三組 gate**，subtitle/summary 皆無） |
 * | summarize_model_family        | str                     | 'gemma4'      | string, default 'gemma4'（advanced；visibleWhen summarize===true） |
 * | summarize_model_size          | str                     | '4b'          | string, default '4b'（advanced；同上）            |
 * | summarize_quantization        | Optional[str]           | None          | string（advanced；同上）                         |
 * | summarize_remote              | bool                    | False         | boolean, default false（advanced；同上）         |
 * | summarize_provider            | Optional[str]           | None          | string（advanced；同上）                         |
 * | summarize_conn_id             | Optional[int]           | None          | number（advanced；同上）                         |
 * | summarize_remote_model        | Optional[str]           | None          | string（advanced；同上）                         |
 * | word_timestamps                | bool                   | False         | boolean, default false（advanced——WhisperAdvancedSettings 五欄） |
 * | condition_on_previous_text     | bool                   | True          | boolean, default true（advanced）                |
 * | min_silence_duration_ms        | int（後端無 ge/le）     | 200           | number min100 max2000 step50, default200（advanced；UI range 沿 WhisperAdvancedSettings 硬編，同 subtitle/summary 慣例） |
 * | vad_threshold                  | float（後端無 ge/le）   | 0.3           | number min0.1 max0.9 step0.05, default0.3（advanced；同上） |
 * | keep_names                    | bool                   | True          | boolean, default true（頂層；visibleWhen translate===true） |
 * | translate_style               | str                     | 'colloquial'  | enum TRANSLATE_STYLES, default 'colloquial'（頂層；visibleWhen translate===true） |
 * | glossary                      | Optional[dict[str,str]] | None          | dict（頂層；visibleWhen translate===true；不入 agent） |
 *
 * 佈局鐵則核對（逐欄照搬舊 AudioTranscribePanel.vue）：model/source_language/output_format
 * 三個 top-level form-group；TranslationOptionsPanel（頂層，非 SettingsCollapsible，同舊
 * panel）；summarize toggle + picker（頂層，同舊 panel）；vocal_separation +
 * WhisperAdvancedSettings 五欄在舊 panel 的 SettingsCollapsible 進階區——advanced；
 * translate_* 與 summarize_* 動態模型系七欄各自 advanced（沿 translate.meta/summary.meta/
 * subtitle.meta 既有慣例——「動態模型系欄位標 advanced」）。
 *
 * **與 video.subtitle 的關鍵差異（勿抄錯，batch3-recon.md §5）**：
 * 1. 翻譯 gate＝獨立 `translate` bool 欄位（非 subtitle 的「target_language 非空」判準）——
 *    後端 AudioTranscribeRequest 真的有這個欄位，TranslationOptionsPanel 受控 modelValue 的
 *    enable_translation 直接對映 params.translate，見 TranscribeParams.vue。
 * 2. buildSubmit 的 translate_* 子欄仍鏡射舊 execute()/getParams() 的雙重判準——
 *    `translate===true && target_language 有值` 才送 target_language + 子欄（舊碼
 *    `translationOptions.value?.enableTranslation && translationOptions.value.targetLanguage`
 *    guard 逐字保留）；但 modelRequirements 的 translate 需求只看 `translate===true`（舊
 *    preflight `if (translationOptions.value?.enableTranslation)` 無 targetLanguage 判準）——
 *    两處判準刻意不同，逐字對照舊 execute()/preflight() 兩段程式碼得出，非筆誤。
 * 3. summarize 是第三組 gate（subtitle/summary 皆無）：summarize bool + 7 個 summarize_*
 *    動態模型系欄位，buildSubmit/modelRequirements 與 translate 同構（唯一差異：summarize
 *    無 target_language 對應物、無 keep_names/translate_style/glossary 對應物——後端就是
 *    只有模型選擇 7 欄，無輸出語言/風格/詞彙表概念）。
 * 4. output_format 是 txt/srt（vs subtitle 的 srt/vtt）。
 * 5. source_language 選項由 GET /audio/transcribe/languages 動態載入，本案選擇**元件內
 *    onMounted 載入、且僅 context==='tool' 才發**（pipeline 節點表單不發此 GET，退純文字
 *    輸入——與 subtitle 由外層殼傳 languageOptions prop 的作法不同，subtitle 該由誰載入是
 *    因為 SubtitlePanel.vue 例外殼本來就要自建 GET；transcribe 走標準 ToolParamHost，無殼可
 *    傳 prop，選擇讓元件自己在 tool context 內載入，見 TranscribeParams.vue 檔頭與 task report）。
 * 6. host 走標準 ToolParamHost（非 subtitle 的例外殼）——AudioView transcribe case 直接換
 *    `<ToolParamHost tool-key="audio.transcribe">`，無需另建殼。
 *
 * TRANSLATE_FIELDS/SUMMARIZE_FIELDS composite 覆蓋欄位命名同構（prefix 不同）：encode/decode
 * 用同一組參數化 helper（encodeSubModelToken/decodeSubModelToken），token 格式與
 * subtitle.meta.ts 的 translate token 一致（含 quantization）：本地 'family:size:quantization'、
 * remote 'remote:provider:connId:modelId'（沿 TranslationOptionsPanel.selectedTranslateModel /
 * 舊 AudioTranscribePanel summarize 本地 token 拆解 pattern：`${family}:${size}:${quant}` 三段皆
 * 保留 quant，非 summary.meta 的 llm/vlm 兩段無 quant 格式——recon §5 已核實兩者是同一種
 * pattern，故本檔共用一個參數化 helper、不重複實作）。
 */
import type { ToolParamMeta } from '../types'

export const WHISPER_SIZES = ['tiny', 'base', 'small', 'medium', 'large-v3'] as const
export const TRANSLATE_STYLES = ['colloquial', 'formal', 'literal'] as const

/** 翻譯 composite（'translate_model'）覆蓋的七個後端欄位 */
export const TRANSLATE_FIELDS = [
  'translate_model_family', 'translate_model_size', 'translate_quantization',
  'translate_remote', 'translate_provider', 'translate_conn_id', 'translate_remote_model',
] as const

/** 摘要 composite（'summarize_model'）覆蓋的七個後端欄位（與 TRANSLATE_FIELDS 同構，prefix 不同） */
export const SUMMARIZE_FIELDS = [
  'summarize_model_family', 'summarize_model_size', 'summarize_quantization',
  'summarize_remote', 'summarize_provider', 'summarize_conn_id', 'summarize_remote_model',
] as const

export const META: ToolParamMeta = {
  toolKey: 'audio.transcribe',
  apiPath: '/audio/transcribe',
  labelKey: 'audio.transcribe.task_label',
  taskType: 'audio.transcribe',
  schema: [
    // ── 頂層：model/source_language/output_format（舊 panel top-level） ──────────
    { name: 'model_size', type: 'enum', options: [...WHISPER_SIZES], default: 'medium' },
    { name: 'source_language', type: 'string' },
    { name: 'output_format', type: 'enum', options: ['txt', 'srt'], default: 'txt' },
    // ── 頂層：翻譯主欄位（獨立 translate bool gate + TranslationOptionsPanel 頂層四欄） ──
    { name: 'translate', type: 'boolean', default: false },
    { name: 'target_language', type: 'string', visibleWhen: (p) => p.translate === true },
    { name: 'keep_names', type: 'boolean', default: true, visibleWhen: (p) => p.translate === true },
    { name: 'translate_style', type: 'enum', options: [...TRANSLATE_STYLES], default: 'colloquial', visibleWhen: (p) => p.translate === true },
    { name: 'glossary', type: 'dict', visibleWhen: (p) => p.translate === true },
    // ── 頂層：摘要主欄位（第三組 gate，subtitle/summary 皆無） ──────────────────
    { name: 'summarize', type: 'boolean', default: false },
    // ── advanced：vocal_separation + Whisper 進階五欄（WhisperAdvancedSettings） ──
    { name: 'vocal_separation', type: 'boolean', default: false, advanced: true },
    { name: 'word_timestamps', type: 'boolean', default: false, advanced: true },
    { name: 'condition_on_previous_text', type: 'boolean', default: true, advanced: true },
    { name: 'min_silence_duration_ms', type: 'number', min: 100, max: 2000, step: 50, default: 200, advanced: true },
    { name: 'vad_threshold', type: 'number', min: 0.1, max: 0.9, step: 0.05, default: 0.3, advanced: true },
    { name: 'align', type: 'boolean', default: false, advanced: true },
    // ── advanced：翻譯模型（動態模型系，沿 translate.meta/summary.meta/subtitle.meta 慣例） ──
    { name: 'translate_model_family', type: 'string', default: 'gemma4', advanced: true, visibleWhen: (p) => p.translate === true },
    { name: 'translate_model_size', type: 'string', default: '4b', advanced: true, visibleWhen: (p) => p.translate === true },
    { name: 'translate_quantization', type: 'string', advanced: true, visibleWhen: (p) => p.translate === true },
    { name: 'translate_remote', type: 'boolean', default: false, advanced: true, visibleWhen: (p) => p.translate === true },
    { name: 'translate_provider', type: 'string', advanced: true, visibleWhen: (p) => p.translate === true },
    { name: 'translate_conn_id', type: 'number', advanced: true, visibleWhen: (p) => p.translate === true },
    { name: 'translate_remote_model', type: 'string', advanced: true, visibleWhen: (p) => p.translate === true },
    // ── advanced：摘要模型（動態模型系，同構 translate_*） ──────────────────────
    { name: 'summarize_model_family', type: 'string', default: 'gemma4', advanced: true, visibleWhen: (p) => p.summarize === true },
    { name: 'summarize_model_size', type: 'string', default: '4b', advanced: true, visibleWhen: (p) => p.summarize === true },
    { name: 'summarize_quantization', type: 'string', advanced: true, visibleWhen: (p) => p.summarize === true },
    { name: 'summarize_remote', type: 'boolean', default: false, advanced: true, visibleWhen: (p) => p.summarize === true },
    { name: 'summarize_provider', type: 'string', advanced: true, visibleWhen: (p) => p.summarize === true },
    { name: 'summarize_conn_id', type: 'number', advanced: true, visibleWhen: (p) => p.summarize === true },
    { name: 'summarize_remote_model', type: 'string', advanced: true, visibleWhen: (p) => p.summarize === true },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  /**
   * buildSubmit（逐字鏡射舊 AudioTranscribePanel execute()/getParams()——兩處原本各複製一份
   * ~40 行,收斂成單一 buildSubmit）。payload 不含 file_id（host 注入）。
   *
   * translate_* 子欄的雙重判準（`translate===true && target_language 有值`）刻意保留——
   * TranscribeParams.vue 的 onTranslationChange 在 gate 開啟時一律把 target_language 補
   * 'zh-TW' fallback（同 TranslationOptionsPanel 內建 UI 行為),故實務上 translate===true 時
   * target_language 恆非空;此判準主要防禦 agent/pipeline 直接 setField('translate', true)
   * 但未觸碰 target_language 的邊界情形（沿舊碼的保守判準,不擅自簡化)。
   */
  buildSubmit(params) {
    const payload: Record<string, unknown> = {}
    if (params.source_language) payload.source_language = params.source_language
    payload.model_size = params.model_size ?? 'medium'
    payload.output_format = params.output_format ?? 'txt'
    payload.vocal_separation = params.vocal_separation === true
    payload.word_timestamps = params.word_timestamps === true
    payload.align = params.align === true
    payload.condition_on_previous_text = params.condition_on_previous_text !== false
    payload.min_silence_duration_ms = params.min_silence_duration_ms ?? 200
    payload.vad_threshold = params.vad_threshold ?? 0.3

    const translateEnabled = params.translate === true
    payload.translate = translateEnabled
    if (translateEnabled && params.target_language) {
      payload.target_language = params.target_language
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

    const summarizeEnabled = params.summarize === true
    payload.summarize = summarizeEnabled
    if (summarizeEnabled) {
      if (params.summarize_remote === true) {
        payload.summarize_remote = true
        payload.summarize_provider = params.summarize_provider
        payload.summarize_conn_id = params.summarize_conn_id
        payload.summarize_remote_model = params.summarize_remote_model
      } else {
        payload.summarize_model_family = params.summarize_model_family ?? 'gemma4'
        payload.summarize_model_size = params.summarize_model_size ?? '4b'
        if (params.summarize_quantization) payload.summarize_quantization = params.summarize_quantization
      }
    }

    return {
      apiPath: META.apiPath,
      payload,
      taskType: META.taskType,
      labelKey: META.labelKey,
    }
  },
  /**
   * 複數模型需求（鏡射舊 AudioTranscribePanel.execute() 開頭四道 guard 依序——whisper →
   * demucs(若 vocal_separation) → align(若 whisperAdvanced.align) → translate(若
   * enableTranslation,**無 targetLanguage 判準**) → summarize(若 summarizeEnabled)。
   * remote 翻譯/摘要不建 requirement（雲端服務,舊碼視為恆 ready,同 subtitle/summary 慣例）。
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
    if (params.translate === true && params.translate_remote !== true) {
      const req: { slot: string; family?: string; size?: string; quantization?: string } = {
        slot: 'translate',
        family: (params.translate_model_family as string | undefined) ?? 'gemma4',
        size: (params.translate_model_size as string | undefined) ?? '4b',
      }
      if (params.translate_quantization) req.quantization = params.translate_quantization as string
      reqs.push(req)
    }
    if (params.summarize === true && params.summarize_remote !== true) {
      const req: { slot: string; family?: string; size?: string; quantization?: string } = {
        slot: 'summarize',
        family: (params.summarize_model_family as string | undefined) ?? 'gemma4',
        size: (params.summarize_model_size as string | undefined) ?? '4b',
      }
      if (params.summarize_quantization) req.quantization = params.summarize_quantization as string
      reqs.push(req)
    }
    return reqs
  },
  // 舊 AudioView.handleMultiExecute 的 'transcribe' case 已支援批次（submitToAll）——沿舊行為。
  multiSelect: true,
  // 舊 AudioTranscribePanel.agentSchema.execute.label 是 'panel.transcribe.execute'，與
  // labelKey('audio.transcribe.task_label') 不同——沿 volume/separate/interpolate 先例承接。
  // agentRequiresConfirm 不設（舊 panel requiresConfirm=true，與 host 預設相同）。
  agentExecuteLabel: 'panel.transcribe.execute',
  persistedModelFields: ['model_size', ...TRANSLATE_FIELDS, ...SUMMARIZE_FIELDS],
}

/**
 * translate_* 與 summarize_* 七欄 model token 的參數化 encode/decode（prefix 區分
 * 'translate'/'summarize'，見檔頭「TRANSLATE_FIELDS/SUMMARIZE_FIELDS composite」註解）。
 * local: 'family:size:quantization'；remote: 'remote:provider:connId:modelId'（沿
 * TranslationOptionsPanel.selectedTranslateModel / subtitle.meta.ts encodeTranslateToken 既有
 * token 慣例——含 quantization，與 summary.meta 的 encodeModelToken(llm/vlm，無 quant)不同構）。
 */
export function encodeSubModelToken(params: Record<string, unknown>, prefix: 'translate' | 'summarize'): string {
  if (params[`${prefix}_remote`] === true) {
    const provider = params[`${prefix}_provider`] != null ? String(params[`${prefix}_provider`]) : ''
    const connId = params[`${prefix}_conn_id`] != null ? String(params[`${prefix}_conn_id`]) : ''
    const modelId = params[`${prefix}_remote_model`] != null ? String(params[`${prefix}_remote_model`]) : ''
    return `remote:${provider}:${connId}:${modelId}`
  }
  const family = params[`${prefix}_model_family`] != null ? String(params[`${prefix}_model_family`]) : ''
  const size = params[`${prefix}_model_size`] != null ? String(params[`${prefix}_model_size`]) : ''
  const quant = params[`${prefix}_quantization`] != null ? String(params[`${prefix}_quantization`]) : ''
  // family/size 皆空 → 回傳空字串,不回傳 '::'（同 subtitle.meta M1 修復——避免無意義 token
  // 被寫進 localStorage/usePersistedModel）。
  if (!family && !size) return ''
  return `${family}:${size}:${quant}`
}

/** decode 回傳明確覆蓋全七欄（undefined＝清除殘值),語意同 subtitle.meta.ts decodeTranslateToken。 */
export function decodeSubModelToken(token: string, prefix: 'translate' | 'summarize'): Record<string, unknown> {
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
      [`${prefix}_quantization`]: undefined,
    }
  }
  const [family, size, quantization] = token.split(':')
  return {
    [`${prefix}_remote`]: false,
    [`${prefix}_provider`]: undefined,
    [`${prefix}_conn_id`]: undefined,
    [`${prefix}_remote_model`]: undefined,
    [`${prefix}_model_family`]: family || undefined,
    [`${prefix}_model_size`]: size || undefined,
    [`${prefix}_quantization`]: quantization || undefined,
  }
}
