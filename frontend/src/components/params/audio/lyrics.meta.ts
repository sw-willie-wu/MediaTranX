/**
 * audio.lyrics 參數 META（統一參數元件 spec §4；批 3 Task 3.5——批 3 收官，照 transcribe.meta.ts
 * 裁剪：lyrics 是 transcribe 的子集，見檔頭「與 audio.transcribe 的關鍵差異」）。
 * schema 準繩＝後端 LyricsRequest（backend/app/api/routes/audio/lyrics.py）全集（file_id/
 * suppress_results 除外）＝15 欄。
 *
 * 後端欄位核對表：
 * | 後端欄位                | 型別                     | 後端 default   | schema 對應 |
 * |--------------------------|--------------------------|---------------|----------------------------------------------------|
 * | model_size                | str                     | 'medium'      | enum WHISPER_SIZES, default 'medium'（頂層）        |
 * | align                     | bool                    | False         | boolean, default false（advanced——舊 SettingsCollapsible） |
 * | translate                 | bool                    | False         | boolean, default false（頂層——獨立 gate，同 transcribe，非 subtitle 的 target_language 非空判準） |
 * | target_language           | Optional[str]           | None          | string（頂層；visibleWhen translate===true）         |
 * | translate_model_family    | str                     | 'gemma4'      | string, default 'gemma4'（advanced；同上）           |
 * | translate_model_size      | str                     | '4b'          | string, default '4b'（advanced；同上）               |
 * | translate_quantization    | Optional[str]           | None          | string（advanced；同上）                             |
 * | translate_remote          | bool                    | False         | boolean, default false（advanced；同上）             |
 * | translate_provider        | Optional[str]           | None          | string（advanced；同上）                             |
 * | translate_conn_id         | Optional[int]           | None          | number（advanced；同上）                             |
 * | translate_remote_model    | Optional[str]           | None          | string（advanced；同上）                             |
 * | output_format              | str                    | 'lrc'         | enum [lrc/txt], default 'lrc'（頂層）                |
 * | keep_names                | bool                    | True          | boolean, default true（頂層；visibleWhen translate===true） |
 * | translate_style           | str                     | 'colloquial'  | enum TRANSLATE_STYLES, default 'colloquial'（頂層；同上） |
 * | glossary                  | Optional[dict[str,str]] | None          | dict（頂層；visibleWhen translate===true；不入 agent） |
 *
 * 佈局鐵則核對（逐欄照搬舊 AudioLyricsPanel.vue）：model/output_format 兩個 top-level
 * form-group；TranslationOptionsPanel（頂層，非 SettingsCollapsible，同舊 panel）；align 在
 * 舊 panel 的 SettingsCollapsible 進階區（`audio_lyrics_advanced`）——advanced；translate_*
 * 動態模型系七欄各自 advanced（沿 transcribe.meta 既有慣例）。**無 vocal_separation UI（服務層
 * 硬編碼強制執行，見下方差異 2）、無 summarize（transcribe 獨有）。**
 *
 * **與 audio.transcribe 的關鍵差異（勿抄錯，batch3-recon.md §6）**：
 * 1. 無 source_language 欄位（後端 LyricsRequest 沒有這個欄位）。
 * 2. 無 vocal_separation 開關：後端服務層永遠對 lyrics 執行 Demucs 人聲分離（無論 UI
 *    有無勾選），故 modelRequirements 對 demucs 的 requirement 是**無條件**推入（非
 *    transcribe 的 `if (vocal_separation===true)` 判準）——舊 AudioLyricsPanel.execute()
 *    對應寫死 `guardModelReady(demucsReady.value, 'audio')` 無 if 包裹，逐字鏡射。
 * 3. 無 summarize（第三組 gate，transcribe 獨有）——lyrics 只有 whisper/demucs/align/translate
 *    四道 modelRequirements（transcribe 五道）。
 * 4. output_format 是 lrc/txt（vs transcribe 的 txt/srt）。
 * 5. 舊 AudioLyricsPanel **無 agentSchema/useAgentPanelHost**（同 audio.cut）——host 自動曝
 *    欄位是行為新增（沿 audio.cut 先例接受），agentExecuteLabel/agentRequiresConfirm 皆不設、
 *    退回 host 預設（labelKey='audio.lyrics.task_label'——沿用舊 submitTask 既有 i18n key、
 *    requiresConfirm=true）。
 * 6. host 走標準 ToolParamHost（非例外殼）——AudioView lyrics case 換
 *    `<ToolParamHost tool-key="audio.lyrics">`，取代舊 `<AudioLyricsPanel>` 直接掛載。
 * 7. 舊 AudioLyricsPanel props 無 isMultiSelect，但 AudioView.handleMultiExecute 原本仍有
 *    'lyrics' case（直呼 panel.getParams()）——遷移後比照 transcode/volume/transcribe 統一走
 *    host 的 isMultiSelect prop + getSubmitSpec()，multiSelect:true（沿舊行為，見 task report）。
 *
 * encodeTranslateToken/decodeTranslateToken 為本檔獨立實作（'translate' 單一 prefix，非
 * transcribe.meta.ts 的參數化 encodeSubModelToken/decodeSubModelToken——沿 subtitle.meta.ts
 * 檔頭先例「不共用,獨立實作」：每個域的 meta 檔各自擁有自己的 token helper，'元件 import 自己的
 * meta' 慣例不跨檔共用純函式）。token 格式與 transcribe/subtitle 一致：本地
 * 'family:size:quantization'、remote 'remote:provider:connId:modelId'。
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
  toolKey: 'audio.lyrics',
  apiPath: '/audio/lyrics',
  labelKey: 'audio.lyrics.task_label',
  taskType: 'audio.lyrics',
  schema: [
    // ── 頂層：model/output_format（舊 panel top-level） ──────────────────────
    { name: 'model_size', type: 'enum', options: [...WHISPER_SIZES], default: 'medium' },
    { name: 'output_format', type: 'enum', options: ['lrc', 'txt'], default: 'lrc' },
    // ── 頂層：翻譯主欄位（獨立 translate bool gate + TranslationOptionsPanel 頂層四欄） ──
    { name: 'translate', type: 'boolean', default: false },
    { name: 'target_language', type: 'string', visibleWhen: (p) => p.translate === true },
    { name: 'keep_names', type: 'boolean', default: true, visibleWhen: (p) => p.translate === true },
    { name: 'translate_style', type: 'enum', options: [...TRANSLATE_STYLES], default: 'colloquial', visibleWhen: (p) => p.translate === true },
    { name: 'glossary', type: 'dict', visibleWhen: (p) => p.translate === true },
    // ── advanced：align（舊 panel SettingsCollapsible 唯一欄） ───────────────
    { name: 'align', type: 'boolean', default: false, advanced: true },
    // ── advanced：翻譯模型（動態模型系，沿 transcribe.meta 慣例） ─────────────
    { name: 'translate_model_family', type: 'string', default: 'gemma4', advanced: true, visibleWhen: (p) => p.translate === true },
    { name: 'translate_model_size', type: 'string', default: '4b', advanced: true, visibleWhen: (p) => p.translate === true },
    { name: 'translate_quantization', type: 'string', advanced: true, visibleWhen: (p) => p.translate === true },
    { name: 'translate_remote', type: 'boolean', default: false, advanced: true, visibleWhen: (p) => p.translate === true },
    { name: 'translate_provider', type: 'string', advanced: true, visibleWhen: (p) => p.translate === true },
    { name: 'translate_conn_id', type: 'number', advanced: true, visibleWhen: (p) => p.translate === true },
    { name: 'translate_remote_model', type: 'string', advanced: true, visibleWhen: (p) => p.translate === true },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  /**
   * buildSubmit（逐字鏡射舊 AudioLyricsPanel execute()/getParams()——兩處原本各複製一份，
   * 收斂成單一 buildSubmit）。payload 不含 file_id（host 注入）。
   *
   * translate_* 子欄的雙重判準（`translate===true && target_language 有值`）刻意保留，同
   * transcribe.meta.ts buildSubmit 註解——沿舊 execute()/getParams() 逐字對照。
   */
  buildSubmit(params) {
    const payload: Record<string, unknown> = {}
    payload.model_size = params.model_size ?? 'medium'
    payload.align = params.align === true
    payload.output_format = params.output_format ?? 'lrc'

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

    return {
      apiPath: META.apiPath,
      payload,
      taskType: META.taskType,
      labelKey: META.labelKey,
    }
  },
  /**
   * 複數模型需求（鏡射舊 AudioLyricsPanel.execute() 開頭三道 guard 依序——whisper → demucs
   * (**無條件**,見檔頭差異 2) → align(若 alignEnabled) → translate(若 enableTranslation,
   * **無 targetLanguage 判準**)。remote 翻譯不建 requirement（雲端服務,舊碼視為恆 ready，
   * 同 transcribe/subtitle 慣例）。
   */
  modelRequirements(params) {
    const reqs: Array<{ slot: string; family?: string; size?: string; quantization?: string; variant?: string; categories?: string[] }> = []
    reqs.push({ slot: 'whisper', variant: String(params.model_size ?? ''), categories: ['stt'] })
    // demucs 無條件推入（服務層永遠對 lyrics 執行人聲分離，見檔頭差異 2——非 transcribe 的
    // vocal_separation===true 判準）。
    reqs.push({ slot: 'separate', variant: 'htdemucs_6s', family: 'demucs', categories: ['separate'] })
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
    return reqs
  },
  // 舊 AudioView.handleMultiExecute 的 'lyrics' case 已支援批次（submitToAll，直呼
  // panel.getParams()——舊 panel props 雖無 isMultiSelect,但 multi 呼叫路徑存在,見檔頭差異 7）。
  multiSelect: true,
  persistedModelFields: ['model_size', ...TRANSLATE_FIELDS],
}

/**
 * 翻譯模型 token encode/decode（'translate_' 前綴七欄；本檔獨立實作，不共用
 * transcribe.meta.ts 的參數化版本，見檔頭說明）。local: 'family:size:quantization'；
 * remote: 'remote:provider:connId:modelId'。
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
  // family/size 皆空 → 回傳空字串,不回傳 '::'（同 subtitle/transcribe.meta M1 修復——避免
  // 無意義 token 被寫進 localStorage/usePersistedModel）。
  if (!family && !size) return ''
  return `${family}:${size}:${quant}`
}

/** decode 回傳明確覆蓋全七欄（undefined＝清除殘值),語意同 transcribe.meta.ts decodeSubModelToken。 */
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
