import { onMounted, onUnmounted, ref } from 'vue'

/**
 * 追蹤 Space 是否按住（全 app 統一互動慣例：拖曳畫面＝Space+左鍵）。
 * 焦點在可互動元素（輸入框/按鈕等）時 Space 有本職，不搶、不 preventDefault。
 * 視窗失焦時重置（避免 Alt-Tab 後卡在按住狀態）。
 */
export function useSpaceHeld() {
  const isSpaceHeld = ref(false)

  function isInteractiveTarget(e: KeyboardEvent): boolean {
    const el = e.target as HTMLElement | null
    return !!el?.closest?.('input, textarea, select, button, [contenteditable="true"]')
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.code === 'Space' && !e.repeat && !isInteractiveTarget(e)) {
      e.preventDefault()
      isSpaceHeld.value = true
    }
  }
  function onKeyUp(e: KeyboardEvent) {
    if (e.code === 'Space') isSpaceHeld.value = false
  }
  function onBlur() {
    isSpaceHeld.value = false
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

  return { isSpaceHeld }
}
