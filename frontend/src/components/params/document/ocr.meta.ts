/**
 * document.ocr 參數 META（統一參數元件 spec §4；批 4 Task 4.4）。
 * schema 準繩＝後端 DocumentOcrRequest 全集（backend/app/api/routes/document/ocr.py）——
 * 與 backend/app/api/routes/image/ocr.py 的 ImageOcrRequest **欄位逐一相同**（output_format/
 * model_family/model_size/quantization/remote/provider/conn_id/remote_model），連 route 內部
 * 分流邏輯（remote+provider+remote_model→submit_remote，否則本地 family/size/quantization）
 * 也逐行一致——兩個路由是同一套 VLM OCR 邏輯分別接在 document/image 兩個檔案服務上。
 *
 * 因此本檔 buildOcrMeta() 是 image.ocr／document.ocr 共用的 META 工廠（僅 toolKey/apiPath/
 * labelKey/taskType/agentExecuteLabel 隨掛載點不同）；image/ocr.meta.ts 直接呼叫本檔匯出的
 * 工廠與 encode/decode token 函式，不重複定義 schema（見該檔）。Params.vue 亦共用同一份
 * 元件（document/OcrParams.vue，image.ocr 的 PARAM_COMPONENTS 條目指到同一檔）——ImageOcrPanel.vue
 * 與 DocumentOcrPanel.vue 逐行比對後只有兩處差異：(1) document 版多一個 currentFileExt prop
 * 驅動的 isPdfOrImage disabled 判斷（validate 只吃 params 做不到，留在 View 層算，見
 * DocumentView.vue ocr 掛載點）；(2) localStorage persist key 不同（doc_ocr_model／
 * image_ocr_model，沿用舊字面值，見 OcrParams.vue persistKey 選配 prop 的檔頭註解）。
 *
 * ⚠ 兩隻舊 panel 皆有額外一道 `GET .../ocr/status?model_family=&size=` 探測（checkAvailable，
 * 顯示「找不到 server」info-box），本案刻意不遷移——現有已遷移的模型系工具（translate/
 * enhance/interpolate/summary 的 vlm 分支）都不做這層前置探測，一律靠 modelRequirement ×
 * ToolParamHost.preflight（isModelInstalled 對 modelStore 下載狀態的比對）在 execute() 前
 * guard，行為與這道探測要達成的目的（提示模型未就緒）等價，維持全案一致性優先於保留這個
 * 舊有的、本案其他工具都沒有的旁支 UI。
 *
 * ⚠ modelRequirement 的 family fallback：後端 model_family=None 時用
 * language_service.get_default_vlm_model()（backend/app/utils/prompts.py DEFAULT_VLM_MODEL=
 * 'qwen3vl'）決定實際家族。前端 meta 純函式不能呼叫後端，故把這個常數複製一份
 * （DEFAULT_VLM_FAMILY）——僅在 model_family 仍是 undefined 時才會用到這個 fallback：正常
 * 使用流程下 OcrParams.vue 的 picker 掛載後會自動選一個實際已下載的 family（seed/fallback
 * watch，同 translate/enhance pattern），model_family 不會停留在 undefined，此 fallback 只
 * 是防禦「清單尚未載入/皆未下載」時 guard 仍能給出一個合理判斷依據（而非直接以 undefined
 * family 誤配到任意 family 的同 size 模型）。
 */
import type { ParamField } from '@/pipeline/types'
import type { ToolParamMeta } from '../types'

/** 後端 language_service.py DEFAULT_VLM_MODEL 常量鏡射（backend/app/utils/prompts.py）。 */
const DEFAULT_VLM_FAMILY = 'qwen3vl'

/** composite 覆蓋的七個後端欄位（model picker token 展開/收斂的目標集）。 */
export const MODEL_FIELDS = [
  'model_family', 'model_size', 'quantization',
  'remote', 'provider', 'conn_id', 'remote_model',
] as const

function ocrSchema(): ParamField[] {
  return [
    { name: 'output_format', type: 'enum', options: ['md', 'txt'], default: 'md' },
    { name: 'model_family', type: 'string', advanced: true },
    { name: 'model_size', type: 'string', default: '4b', advanced: true },
    { name: 'quantization', type: 'string', advanced: true },
    { name: 'remote', type: 'boolean', default: false, advanced: true },
    { name: 'provider', type: 'string', advanced: true },
    { name: 'conn_id', type: 'number', advanced: true },
    { name: 'remote_model', type: 'string', advanced: true },
  ]
}

export interface BuildOcrMetaOptions {
  toolKey: string
  apiPath: string
  labelKey: string
  taskType: string
  agentExecuteLabel: string
}

/** image.ocr／document.ocr 共用的 META 工廠（見檔頭註解）。 */
export function buildOcrMeta(opts: BuildOcrMetaOptions): ToolParamMeta {
  return {
    toolKey: opts.toolKey,
    apiPath: opts.apiPath,
    labelKey: opts.labelKey,
    taskType: opts.taskType,
    schema: ocrSchema(),
    defaults() {
      const d: Record<string, unknown> = {}
      for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
      return d
    },
    // 舊 getParams() 原樣透傳；file_id 由 host 注入——無需 buildSubmit 特殊清理。
    // remote=true → 雲端服務，不需本地模型下載；否則以 family/size/quantization 查 host 的
    // useModelGuard 下載狀態；family fallback 見檔頭註解。
    modelRequirement(params) {
      if (params.remote === true) return null
      return {
        slot: 'ocr',
        family: (params.model_family as string | undefined) ?? DEFAULT_VLM_FAMILY,
        size: (params.model_size as string | undefined) ?? '4b',
        quantization: params.quantization as string | undefined,
      }
    },
    // 舊 View.handleMultiExecute 的 'ocr' case 已支援批次（submitToAll）——沿舊行為。
    multiSelect: true,
    // TextPreviewModal/下載格式契約（DocumentView.vue 既有 :format="ocrPanelRef?.outputFormat"）
    // ——host 據此 expose outputFormat，遷移後改讀 ToolParamHost.outputFormat。
    downloadFormatField: 'output_format',
    agentExecuteLabel: opts.agentExecuteLabel,
    persistedModelFields: [...MODEL_FIELDS],
  }
}

export const META: ToolParamMeta = buildOcrMeta({
  toolKey: 'document.ocr',
  apiPath: '/document/ocr',
  labelKey: 'document.ocr.task_label',
  taskType: 'document.ocr',
  // 舊 DocumentOcrPanel.agentSchema.execute.label。
  agentExecuteLabel: 'panel.doc_ocr.execute',
})

/**
 * local: 'family:size'；remote: 'remote:provider:connId:modelId'（沿
 * useModelOptions.parseModelValue 的 remote token 慣例）。quantization 不進 token
 * （舊兩隻 panel 的 picker 選項本就以 family:size 去重，quantization 欄位獨立存在於 schema
 * 但 UI 未曝露選擇——decode 時一律清空，見下方函式）。
 */
export function encodeModelToken(params: Record<string, unknown>): string {
  if (params.remote === true) {
    const provider = params.provider != null ? String(params.provider) : ''
    const connId = params.conn_id != null ? String(params.conn_id) : ''
    const modelId = params.remote_model != null ? String(params.remote_model) : ''
    return `remote:${provider}:${connId}:${modelId}`
  }
  const family = params.model_family != null ? String(params.model_family) : ''
  const size = params.model_size != null ? String(params.model_size) : ''
  return `${family}:${size}`
}

/**
 * decode 回傳的 patch 明確覆蓋全七欄——local/remote 互斥分支各自把「另一側」欄位設
 * undefined（同 translate.meta.ts 慣例，undefined 經 JSON.stringify/normalizeParams 丟棄
 * 該鍵，不殘留另一分支的殘值）。
 */
export function decodeModelToken(token: string): Record<string, unknown> {
  if (token.startsWith('remote:')) {
    const parts = token.split(':')
    const connIdRaw = parts[2] ?? ''
    const connIdNum = Number(connIdRaw)
    return {
      remote: true,
      provider: parts[1] || undefined,
      conn_id: connIdRaw !== '' && Number.isFinite(connIdNum) ? connIdNum : undefined,
      remote_model: parts.slice(3).join(':') || undefined,
      model_family: undefined,
      model_size: undefined,
      quantization: undefined,
    }
  }
  const [family, size] = token.split(':')
  return {
    remote: false,
    provider: undefined,
    conn_id: undefined,
    remote_model: undefined,
    model_family: family || undefined,
    model_size: size || undefined,
    quantization: undefined,
  }
}
