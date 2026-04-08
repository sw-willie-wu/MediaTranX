import { ref, watch } from 'vue'

/**
 * Persisted model selection — saves to localStorage and restores on next use.
 * @param key localStorage key (e.g. 'transcribe_whisper_model')
 * @param fallback default value if nothing saved
 */
export function usePersistedModel(key: string, fallback: string = '') {
  const saved = localStorage.getItem(key)
  const value = ref(saved ?? fallback)
  watch(value, (v) => {
    if (v) localStorage.setItem(key, v)
  })
  return value
}
