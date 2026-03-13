import { ref, watch, onMounted } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'

const themeMode = ref<ThemeMode>('system')
const effectiveTheme = ref<'light' | 'dark'>('dark')

// 取得系統偏好
function getSystemTheme(): 'light' | 'dark' {
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return 'dark'
}

// 更新實際主題
function updateEffectiveTheme() {
  if (themeMode.value === 'system') {
    effectiveTheme.value = getSystemTheme()
  } else {
    effectiveTheme.value = themeMode.value
  }

  // 套用到 document
  document.documentElement.setAttribute('data-theme', effectiveTheme.value)
}

// 設定主題
function setTheme(mode: ThemeMode) {
  themeMode.value = mode
  localStorage.setItem('theme-mode', mode)
  updateEffectiveTheme()
}

// 初始化
function initTheme() {
  // 從 localStorage 讀取
  const saved = localStorage.getItem('theme-mode') as ThemeMode | null
  if (saved && ['light', 'dark', 'system'].includes(saved)) {
    themeMode.value = saved
  }

  updateEffectiveTheme()

  // 監聽系統主題變化
  if (typeof window !== 'undefined' && window.matchMedia) {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    mediaQuery.addEventListener('change', () => {
      if (themeMode.value === 'system') {
        updateEffectiveTheme()
      }
    })
  }
}

export function useTheme() {
  onMounted(() => {
    initTheme()
  })

  return {
    themeMode,
    effectiveTheme,
    setTheme,
    initTheme,
  }
}

// 立即初始化（避免閃爍）
if (typeof window !== 'undefined') {
  const saved = localStorage.getItem('theme-mode') as ThemeMode | null
  const mode = saved && ['light', 'dark', 'system'].includes(saved) ? saved : 'system'
  const theme = mode === 'system' ? getSystemTheme() : mode
  document.documentElement.setAttribute('data-theme', theme)
}
