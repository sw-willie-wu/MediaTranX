/**
 * 畫布鍵盤快捷鍵判定純函式（spec F2/F3，2026-07-16 畫布 UX 批次）——
 * 抽離 PipelineView 以便單元測試；view 層負責掛卸與 store/VueFlow 接線。
 */

export type CanvasKeyAction = 'connect' | 'undo' | 'redo' | 'copy' | 'paste'

/** 焦點在輸入類元素：所有畫布快捷鍵讓路（Ctrl+C 的文字複製等本職不攔） */
export function isEditableTarget(e: KeyboardEvent): boolean {
  const el = e.target as HTMLElement | null
  return !!el?.closest?.('input, textarea, select, [contenteditable="true"]')
}

/**
 * 快捷鍵 → 動作：
 * - C（無任何修飾鍵）＝連線選取的兩節點
 * - Ctrl/Cmd+Z＝undo、Ctrl/Cmd+Y 與 Ctrl/Cmd+Shift+Z＝redo（Windows 慣例並存）
 * - Ctrl/Cmd+C＝複製、Ctrl/Cmd+V＝貼上
 */
export function matchShortcut(e: KeyboardEvent): CanvasKeyAction | null {
  const mod = e.ctrlKey || e.metaKey
  const k = e.key.toLowerCase()
  if (!mod) {
    if (k === 'c' && !e.altKey && !e.shiftKey) return 'connect'
    return null
  }
  if (e.altKey) return null
  if (k === 'z') return e.shiftKey ? 'redo' : 'undo'
  if (k === 'y' && !e.shiftKey) return 'redo'
  if (k === 'c' && !e.shiftKey) return 'copy'
  if (k === 'v' && !e.shiftKey) return 'paste'
  return null
}

export interface ConnectCandidate {
  id: string
  x: number
  y: number
}

/**
 * C 鍵方向判定（spec F2）：恰 2 個選取節點時，以 (x, y, id) 排序（tie-break
 * 穩定）先試 左→右，失敗試 右→左；兩向皆不合法回第一次嘗試的錯誤。
 * 選取數 ≠ 2 回 null（no-op）。root 節點照常參與（root→tool 是最常見連線）。
 */
export function pickConnectPair(
  selected: ConnectCandidate[],
  tryConnect: (from: string, to: string) => string | null,
): { from: string; to: string } | { error: string } | null {
  if (selected.length !== 2) return null
  const [l, r] = [...selected].sort((a, b) =>
    a.x - b.x || a.y - b.y || (a.id < b.id ? -1 : 1))
  const firstErr = tryConnect(l.id, r.id)
  if (firstErr === null) return { from: l.id, to: r.id }
  if (tryConnect(r.id, l.id) === null) return { from: r.id, to: l.id }
  return { error: firstErr }
}
