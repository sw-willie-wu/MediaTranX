import { createI18n } from 'vue-i18n'
import zhTW from './locales/zh-TW'
import en from './locales/en'

export type SupportedLocale = 'zh-TW' | 'en'
export const LOCALE_OPTIONS = [
  { value: 'zh-TW', label: '繁體中文' },
  { value: 'en', label: 'English' },
] as const

const STORAGE_KEY = 'app-locale'

function detectSystemLocale(): SupportedLocale {
  const lang = navigator.language // e.g. "zh-TW", "en-US"
  if (lang.startsWith('zh')) return 'zh-TW'
  return 'en'
}

export function resolveLocale(): SupportedLocale {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved === 'zh-TW' || saved === 'en') return saved
  return detectSystemLocale()
}

export function saveLocalePreference(value: SupportedLocale) {
  localStorage.setItem(STORAGE_KEY, value)
  // Sync to Electron preferences (for splash screen locale)
  ;(window as any).electron?.savePreference('locale', value)
}

export function getSavedPreference(): SupportedLocale {
  return resolveLocale()
}

const i18n = createI18n({
  legacy: false,
  locale: resolveLocale(),
  fallbackLocale: 'en',
  messages: { 'zh-TW': zhTW, en },
})

export default i18n
