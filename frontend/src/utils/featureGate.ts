/**
 * Feature gate：節點模式（流程畫布）依 update channel 隱藏。
 * spec: .claude/specs/pipeline-feature-gate.md §3.2
 */
export function isPipelineEnabled(): boolean {
  // typeof 守衛必要：TOOLS = getTools(null) 在 module load 求值，而
  // useAgent.test.ts 是 @vitest-environment node（無 window），import 鏈上
  // 裸讀 window 會在測試 stub 生效前就 ReferenceError（ESM：被匯入模組先於
  // 測試檔本體求值）。比照 stores/update.ts:37 的既有寫法。
  const electron = typeof window !== 'undefined' ? window.electron : undefined
  if (!electron) return true // 純瀏覽器（開發/e2e）：無 preload、無洩漏疑慮，直接開
  // Electron 下 fail-safe：只有「明確收到 dev」才開。注入斷掉（arg 名打錯、
  // 舊 preload）→ 隱藏——方向與 resolveChannel 對 buildMode 缺省視同 stable 一致，
  // 且故障徵兆是「dev Electron 看不到流程按鈕」，日常開發立即自我暴露；
  // 反向（fail-open）的故障徵兆是 stable 洩漏未驗收功能且無人察覺。
  return electron.updateChannel === 'dev'
}
