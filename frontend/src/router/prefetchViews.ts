/**
 * Results 抽屜開啟＝「即將 open-in-tool」的強意圖訊號——先把四個工具頁 chunk 抓下來，
 * 讓 openInTool 的 router.push 幾乎即時（切頁前唯一 await 就是 chunk dynamic import）。
 * import specifier 與 router/index.ts 完全一致（Vite 同模組去重、命中同一 chunk）。
 */
const DEFAULT_LOADERS: Array<() => Promise<unknown>> = [
  () => import('../views/ImageView.vue'),
  () => import('../views/VideoView.vue'),
  () => import('../views/AudioView.vue'),
  () => import('../views/DocumentView.vue'),
]

let done = false

export function prefetchToolViews(loaders: Array<() => Promise<unknown>> = DEFAULT_LOADERS): void {
  if (done) return
  done = true
  for (const load of loaders) {
    try {
      load().catch(() => { /* fire-and-forget：離線/chunk 失敗靜默，實際導航時再處理 */ })
    } catch {
      /* 同步拋錯也吞掉——預熱是最佳努力 */
    }
  }
}

/** 測試用：重置 once latch。 */
export function _resetForTest(): void {
  done = false
}
