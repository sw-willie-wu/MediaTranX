import { onMounted, onUnmounted, ref, type Ref } from 'vue'

/**
 * 泛用「按鍵按住」偵測核心（useSpaceHeld 泛化而來，2026-07-16 畫布 UX 批次）。
 * - e.repeat 一律跳過（原 useSpaceHeld 行為：repeat 不重設也不 preventDefault）
 * - skipInteractive：焦點在輸入框/按鈕等可互動元素時不搶（該鍵有本職）
 * - 視窗失焦重置（Alt-Tab 後不卡在按住狀態）
 */
export interface KeyHeldOptions {
  /** 目標鍵判定（keydown/keyup 共用） */
  match: (e: KeyboardEvent) => boolean
  /** keydown 時 preventDefault（如 Space 防捲動）；預設 false */
  preventDefault?: boolean
  /** 焦點在 input/textarea/select/button/contenteditable 時忽略 keydown；預設 false */
  skipInteractive?: boolean
}

export function useKeyHeld(opts: KeyHeldOptions): { isHeld: Ref<boolean> } {
  const isHeld = ref(false)

  function isInteractiveTarget(e: KeyboardEvent): boolean {
    const el = e.target as HTMLElement | null
    return !!el?.closest?.('input, textarea, select, button, [contenteditable="true"]')
  }

  function onKeyDown(e: KeyboardEvent) {
    if (!opts.match(e) || e.repeat) return
    if (opts.skipInteractive && isInteractiveTarget(e)) return
    if (opts.preventDefault) e.preventDefault()
    isHeld.value = true
  }
  function onKeyUp(e: KeyboardEvent) {
    if (opts.match(e)) isHeld.value = false
  }
  function onBlur() {
    isHeld.value = false
  }

  onMounted(() => {
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    window.addEventListener('blur', onBlur)
  })
  onUnmounted(() => {
    window.removeEventListener('keydown', onKeyDown)
    window.removeEventListener('keyup', onKeyUp)
    window.removeEventListener('blur', onBlur)
  })

  return { isHeld }
}

/**
 * 追蹤 Shift 是否按住（畫布 Shift 點擊連線用）。
 * 不 preventDefault（Shift 是修飾鍵無預設行為）、不 skipInteractive
 * （只讀旗標，輸入框內按 Shift 不受影響也不影響輸入）。
 */
export function useShiftHeld() {
  const { isHeld } = useKeyHeld({ match: (e) => e.key === 'Shift' })
  return { isShiftHeld: isHeld }
}
