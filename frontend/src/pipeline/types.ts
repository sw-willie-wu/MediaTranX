/**
 * Node Pipeline 核心型別（spec §3 B1/B2）。
 * registry 是唯一事實來源:param_schema 供三方共用——畫布表單生成、
 * recipe 驗證、agent create_pipeline 的 JSON 驗證。
 */
import type { MediaKindT } from '@/utils/mediaKind'

export type { MediaKindT }

export interface ParamField {
  name: string
  type: 'enum' | 'number' | 'boolean' | 'string' | 'dict' | 'list'
  default?: unknown
  /** enum 選項（靜態；動態選項欄位 v1 不建模，落 advanced 原樣透傳） */
  options?: string[]
  min?: number
  max?: number
  step?: number
  /** 收進 SettingsCollapsible 的進階區 */
  advanced?: boolean
  /** 條件顯示（僅影響表單 UI，驗證仍全欄位過） */
  visibleWhen?: (params: Record<string, unknown>) => boolean
  /** list 元素型別（選配；未宣告時不檢查元素型別） */
  itemType?: 'string' | 'number'
  /** 給 LLM 的欄位說明（選配） */
  agentHint?: string
}

export interface ToolSpec {
  /** 'video.transcode' — 同 taskType */
  toolKey: string
  /** POST 路徑，如 '/video/transcode' */
  apiPath: string
  /** i18n label key（沿用各工具面板既有 key） */
  labelKey: string
  /** 'tool' = 單輸入；'source' = 零輸入生成（v1 僅 video.download） */
  kind: 'tool' | 'source'
  /** 接受的輸入媒體類別（source 為空陣列） */
  inputKinds: MediaKindT[]
  /** 副檔名級 refinement（選配；宣告了就以它為準，如 document.split 只吃 pdf） */
  inputExts?: string[]
  /** 產出媒體類別 — 參數的函數（如 video.transcode 出 gif/apng 算 image） */
  outputKind: (params: Record<string, unknown>) => MediaKindT
  paramSchema: ParamField[]
}

// ── Recipe（B1）──────────────────────────────────────────────────────

export interface RecipeNode {
  id: string
  kind: 'input' | 'source' | 'tool'
  /** kind='tool'|'source' 時必填 */
  toolKey?: string
  params: Record<string, unknown>
  /** 非末端節點預設 suppress;true = 該節點產出仍進 results drawer */
  keepOutput?: boolean
  /** 畫布座標（引擎不使用） */
  position?: { x: number; y: number }
}

export interface RecipeEdge {
  from: string
  to: string
}

export interface Recipe {
  version: 1
  name: string
  nodes: RecipeNode[]
  edges: RecipeEdge[]
}

export interface ValidationIssue {
  severity: 'error' | 'warning'
  nodeId?: string
  edge?: RecipeEdge
  code:
    | 'cycle'
    | 'multi_root'
    | 'no_root'
    | 'tool_indegree'
    | 'edge_endpoint'
    | 'kind_mismatch'
    | 'unknown_tool'
    | 'param_invalid'
    | 'param_unknown'
    | 'orphan_node'
    | 'source_has_input'
    | 'param_semantic'
    | 'model_missing'
  message: string
}
