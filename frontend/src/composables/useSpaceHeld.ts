import { useKeyHeld } from './useKeyHeld'

/**
 * 追蹤 Space 是否按住（全 app 統一互動慣例：拖曳畫面＝Space+左鍵）。
 * 焦點在可互動元素（輸入框/按鈕等）時 Space 有本職，不搶、不 preventDefault。
 * 視窗失焦時重置（避免 Alt-Tab 後卡在按住狀態）。
 * （核心邏輯泛化至 useKeyHeld；對外 API 與行為不變。）
 */
export function useSpaceHeld() {
  const { isHeld } = useKeyHeld({
    match: (e) => e.code === 'Space',
    preventDefault: true,
    skipInteractive: true,
  })
  return { isSpaceHeld: isHeld }
}
