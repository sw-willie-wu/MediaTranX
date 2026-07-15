/**
 * 畫布視覺判定純函式（spec F4-①/②，2026-07-16 畫布 UX 批次）——
 * 抽離 PipelineView 以便單元測試；issue bar 三態與節點紅框謂詞。
 */
import type { ValidationIssue } from './types'

/**
 * 節點紅框謂詞：error 級 issue（結構＋modelIssues）∪ `tool_unrooted` warning。
 * 「紅框」＝需要使用者注意的節點級標記、非嚴格 error 對映——未生根 head 在
 * v1.7.0 是 error（有紅框），拆碼降 warning 後紅框保留（回報者明示要保留、
 * 零視覺回退）；orphan_node 維持不紅（現狀也沒有）。
 */
export function nodeFlagged(nodeId: string, issues: ValidationIssue[]): boolean {
  return issues.some(i => i.nodeId === nodeId
    && (i.severity === 'error' || i.code === 'tool_unrooted'))
}

export interface BarState {
  tone: 'danger' | 'warning'
  message: string
  /** 「+N」計數（0＝不顯示） */
  extra: number
}

/**
 * issue bar 三態（spec F4-①）：
 * - danger：blocking 結構錯誤 ∪ modelIssues —— 擋 run 或 run 失敗類，紅色
 * - warning：僅剩不可達分支的錯誤 —— 不擋 run、黃色提醒
 * - null：無 error（乾淨懸空鏈只有 warning——由淡化視覺＋紅框承擔，不進 bar）
 * 紅組首條＝blocking 優先於 model（結構錯可在 run 前修正）；
 * 紅組 +N＝blocking+model+advisory−1（黃組僅 advisory−1）。
 */
export function barState(
  blocking: ValidationIssue[],
  advisory: ValidationIssue[],
  modelErrors: ValidationIssue[],
): BarState | null {
  const red = blocking.length + modelErrors.length
  if (red > 0) {
    return {
      tone: 'danger',
      message: (blocking[0] ?? modelErrors[0]).message,
      extra: red + advisory.length - 1,
    }
  }
  if (advisory.length > 0) {
    return { tone: 'warning', message: advisory[0].message, extra: advisory.length - 1 }
  }
  return null
}
