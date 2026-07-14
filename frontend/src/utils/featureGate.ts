/**
 * Feature gate：節點模式（流程畫布）。
 * 1.6.x 期間依 update channel 隱藏（stable 藏、dev 開）——v1.7.0 正式開放，
 * gate 恆 true。保留函式殼：呼叫點（router/側欄/agent 工具/系統提示）不動，
 * 未來新功能要 channel-gate 可循同模式。channel gate 史見
 * spec: .claude/specs/pipeline-feature-gate.md §3.2。
 */
export function isPipelineEnabled(): boolean {
  return true
}
