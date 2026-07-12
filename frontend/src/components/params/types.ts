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
  /**
   * 模型需求：remote/無需求回 null。兩種比對形狀（isModelInstalled 依 req.variant 是否存在
   * 分流，見 modelGuardUtils.ts）：
   * - family/size/quantization：既有路徑（translate 等 size:quantization 組合 variant 系）
   * - variant/categories：批 2 Task 2.3 擴充（interpolate/enhance 等單一 variant token 系，
   *   如 RIFE/Real-ESRGAN；categories 是 modelStore category/subcategory 的查找範圍，family
   *   選配（enhance 用以縮限 realesrgan 家族，interpolate 不需要因單一家族))
   */
  modelRequirement?(params: Record<string, unknown>):
    { slot: string; family?: string; size?: string; quantization?: string; variant?: string; categories?: string[] } | null
  /**
   * 複數模型需求（批 2 Task 2.4 host 擴充——video.summary 三模型系 whisper/demucs/align/
   * llm/vlm 逐一 guard）。與 modelRequirement（單數）並存,host 二擇一讀取(優先讀複數)；
   * 回 null/空陣列＝無需求。第三種比對形狀(見 modelGuardUtils.ts)：無 variant 且無
   * family/size、只有 categories——categories 內任一 downloaded 即視為就緒(align 用)。
   */
  modelRequirements?(params: Record<string, unknown>):
    Array<{ slot: string; family?: string; size?: string; quantization?: string; variant?: string; categories?: string[] }> | null
  multiSelect: boolean
  /** 下載按鈕的輸出格式欄位名（host 據此 expose outputFormat） */
  downloadFormatField?: string
  /** agent 面板 execute 動作的 label i18n key；未設時 host 用 meta.labelKey（批 2 Task 2.3
   *  新增——interpolate/enhance 舊 agentSchema.execute.label 與 labelKey 不同,見兩檔 meta 註解） */
  agentExecuteLabel?: string
  /** agent 面板 execute 動作是否需要確認；未設時 host 預設 true（批 3 Task 3.1 新增——
   *  第一個不同者是 audio.volume，舊 AudioVolumePanel.agentSchema.execute.requiresConfirm
   *  為 false，見 volume.meta.ts 註解） */
  agentRequiresConfirm?: boolean
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
