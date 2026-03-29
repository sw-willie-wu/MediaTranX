/**
 * 可拖曳調整三欄佈局寬度 composable
 *
 * 管理 sidebar / settings panel 的寬度，preview area 自適應剩餘空間。
 * 寬度持久化到 localStorage，並支援重設回預設值。
 */
import { ref, onBeforeUnmount } from 'vue'

const STORAGE_KEY = 'tool-layout-widths'

// MainSidebar = 52px, 讓 sidebar + MainSidebar ≈ settings 讓 preview 視覺置中
const DEFAULTS = { sidebar: 220, settings: 272 }
const LIMITS = {
  sidebar: { min: 120, max: 300 },
  settings: { min: 240, max: 500 },
}

// Singleton refs — 多個 ToolLayout instance (KeepAlive) 共享同一份狀態
const sidebarWidth = ref(DEFAULTS.sidebar)
const settingsWidth = ref(DEFAULTS.settings)

// 從 localStorage 載入
const saved = localStorage.getItem(STORAGE_KEY)
if (saved) {
  try {
    const parsed = JSON.parse(saved)
    if (parsed.sidebar) sidebarWidth.value = Math.max(LIMITS.sidebar.min, Math.min(LIMITS.sidebar.max, parsed.sidebar))
    if (parsed.settings) settingsWidth.value = Math.max(LIMITS.settings.min, Math.min(LIMITS.settings.max, parsed.settings))
  } catch { /* ignore */ }
}

function persist() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    sidebar: sidebarWidth.value,
    settings: settingsWidth.value,
  }))
}

export function useResizableLayout() {
  let cleanupFn: (() => void) | null = null

  function startResize(edge: 'sidebar' | 'settings', event: MouseEvent) {
    event.preventDefault()

    const startX = event.clientX
    const startWidth = edge === 'sidebar' ? sidebarWidth.value : settingsWidth.value
    const limits = LIMITS[edge]
    const widthRef = edge === 'sidebar' ? sidebarWidth : settingsWidth
    // sidebar: 往右拖 → 變寬; settings: 往左拖 → 變寬
    const direction = edge === 'sidebar' ? 1 : -1

    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    function onMouseMove(e: MouseEvent) {
      const delta = (e.clientX - startX) * direction
      widthRef.value = Math.max(limits.min, Math.min(limits.max, startWidth + delta))
    }

    function onMouseUp() {
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
      cleanupFn = null
      persist()
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)

    cleanupFn = () => {
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }

  function resetLayout() {
    sidebarWidth.value = DEFAULTS.sidebar
    settingsWidth.value = DEFAULTS.settings
    localStorage.removeItem(STORAGE_KEY)
  }

  onBeforeUnmount(() => {
    cleanupFn?.()
  })

  return {
    sidebarWidth,
    settingsWidth,
    startResize,
    resetLayout,
  }
}
