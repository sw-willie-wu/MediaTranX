/**
 * document.translate 參數 META（統一參數元件 spec §4；批 1 Task 1.5——model picker
 * composite agent 欄位「首用」打樣，之後 6 個模型系工具套用同一 pattern）。
 * schema 準繩＝後端 DocumentTranslateRequest（backend/app/api/routes/document/translate.py）全集。
 *
 * 後端欄位核對表（file_id/suppress_results 除外——host 層注入/由 buildSubmit 決定，不進 schema）：
 * | 後端欄位          | 型別                    | 後端 default   | schema 對應                                  |
 * |------------------|------------------------|---------------|-----------------------------------------------|
 * | source_language  | str（必填）              | 無             | string（動態語言清單，型別故意不設 enum）        |
 * | target_language  | str（必填）              | 無             | string                                         |
 * | model_size       | str                    | '4b'           | string, default '4b'                          |
 * | model_family     | str                    | 'gemma4'       | string, default 'gemma4'                      |
 * | quantization     | Optional[str]          | None           | string（無 default）                           |
 * | translate_style  | str                    | 'colloquial'   | enum [colloquial/formal/literal], default 同上 |
 * | glossary         | Optional[dict[str,str]]| None           | dict（無 default；v1 dict 型別批 0 已解禁）      |
 * | remote           | bool                   | False          | boolean, default false                        |
 * | provider         | Optional[str]          | None           | string                                         |
 * | conn_id          | Optional[int]          | None           | number                                         |
 * | remote_model     | Optional[str]          | None           | string                                         |
 *
 * model_family/model_size/quantization/remote/provider/conn_id/remote_model 七欄由
 * TranslateParams.vue 註冊的 composite agent 欄位（'translate_model'）取代曝光給 agent
 * （ToolParamHost 兩層合成時以 composite 覆蓋這七欄，見 spec §6 Major 2）；schema 仍完整
 * 列出七欄——工具頁 UI／pipeline 節點表單／validate 準繩不因 agent 層合成而改變。
 */
import type { ToolParamMeta } from '../types'

export const TRANSLATE_STYLES = ['colloquial', 'formal', 'literal'] as const

/** composite 覆蓋的七個後端欄位（model picker token 展開/收斂的目標集） */
export const MODEL_FIELDS = [
  'model_family', 'model_size', 'quantization',
  'remote', 'provider', 'conn_id', 'remote_model',
] as const

export const META: ToolParamMeta = {
  toolKey: 'document.translate',
  apiPath: '/document/translate',
  labelKey: 'document.translate.task_label',
  taskType: 'document.translate',
  schema: [
    { name: 'source_language', type: 'string' },
    { name: 'target_language', type: 'string' },
    { name: 'translate_style', type: 'enum', options: [...TRANSLATE_STYLES], default: 'colloquial' },
    { name: 'glossary', type: 'dict' },
    { name: 'model_family', type: 'string', default: 'gemma4', advanced: true },
    { name: 'model_size', type: 'string', default: '4b', advanced: true },
    { name: 'quantization', type: 'string', advanced: true },
    { name: 'remote', type: 'boolean', default: false, advanced: true },
    { name: 'provider', type: 'string', advanced: true },
    { name: 'conn_id', type: 'number', advanced: true },
    { name: 'remote_model', type: 'string', advanced: true },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  // remote=true → 雲端服務，不需本地模型下載；否則以 family/size/quantization 查 host 的
  // useModelGuard 下載狀態（ToolParamHost.preflight，批 1 Task 1.5 接線）。
  modelRequirement(params) {
    if (params.remote === true) return null
    return {
      slot: 'translate',
      family: params.model_family as string | undefined,
      size: params.model_size as string | undefined,
      quantization: params.quantization as string | undefined,
    }
  },
  // 舊 DocumentView.handleMultiExecute 的 'translate' case 已支援批次（submitToAll）——沿舊行為。
  multiSelect: true,
  persistedModelFields: [...MODEL_FIELDS],
}

/**
 * local: 'family:size:quantization'；remote: 'remote:provider:connId:modelId'
 * （沿 useModelOptions.parseModelValue 的 remote token 慣例）。
 * 純函式：TranslateParams.vue 的 picker UI 衍生值與 composite agent 欄位（get）共用。
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
  const quant = params.quantization != null ? String(params.quantization) : ''
  return `${family}:${size}:${quant}`
}

/**
 * decode 回傳的 patch 明確覆蓋全七欄——local/remote 互斥分支各自把「另一側」欄位設
 * undefined。決定：patch 值用 undefined 表達「清除」而非省略鍵（省略鍵在 host 的
 * `{ ...params, ...patch }` merge 語意下不會清掉舊值，undefined 才會覆蓋掉殘值）。
 * undefined 本身不留髒值：送後端前 payload 經 JSON.stringify（useSubmitTask/apiFetch）
 * 會直接丟棄 value===undefined 的鍵；pipeline 側 normalizeParams（recipe.ts）對
 * value===undefined 的欄位一律 skip（沿用 default 或不送）——兩條路徑皆不殘留另一分支的欄位。
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
  const [family, size, quantization] = token.split(':')
  return {
    remote: false,
    provider: undefined,
    conn_id: undefined,
    remote_model: undefined,
    model_family: family || undefined,
    model_size: size || undefined,
    quantization: quantization || undefined,
  }
}
