/**
 * 統一參數元件層的共用型別（spec：.claude/specs/2026-07-12-unified-param-components-design.md §4/§6）。
 * META 檔（<tool>.meta.ts）與兩側 host 的契約；純型別，不得 import Vue/store。
 */
import type { ParamField } from '@/pipeline/types'

/** host 提交描述：payload 一律不含 file_id（由呼叫端注入——單檔 host execute、批次逐檔） */
export interface SubmitSpec {
  apiPath: string
  payload: Record<string, unknown>
  taskType: string
  labelKey: string
}

export interface ToolParamMeta {
  toolKey: string
  apiPath: string
  labelKey: string
  taskType: string
  /** 後端 request 欄位全集（準繩＝後端 Pydantic model；file_id/suppress_results 除外） */
  schema: ParamField[]
  defaults(): Record<string, unknown>
  /** 跨欄位語意驗證；null=合法，字串=錯誤訊息 i18n key */
  validate?(params: Record<string, unknown>): string | null
  /** 工具頁 endpoint 分流（僅 video 轉檔）；payload 不含 file_id */
  buildSubmit?(params: Record<string, unknown>): SubmitSpec
  /** 模型需求：remote/無需求回 null */
  modelRequirement?(params: Record<string, unknown>):
    { slot: string; family?: string; size?: string; quantization?: string } | null
  multiSelect: boolean
  /** 下載按鈕的輸出格式欄位名（host 據此 expose outputFormat） */
  downloadFormatField?: string
  /** persisted-model seeding 受控欄位 */
  persistedModelFields?: string[]
  /** 檔案載入/切換時 seeding：工具頁 host 對 fileInfo 做 immediate watch 呼叫並 merge patch；
   *  pipeline 不呼叫。 */
  seedOnFileChange?(fileInfo: Record<string, unknown> | null,
    current: Record<string, unknown>): Record<string, unknown> | null
}

/** model picker 元件註冊給 host 的 composite agent 欄位（覆蓋後端欄位群、供即時選項） */
export interface AgentCompositeField {
  name: string
  covers: string[]
  options: () => string[]
  get(params: Record<string, unknown>): string
  set(token: string): Record<string, unknown>
}
