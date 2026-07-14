import { ref, watch, toValue, type MaybeRefOrGetter } from 'vue'

export interface UsePersistedModelOptions {
  /**
   * When false, disables both localStorage seeding (initial value stays the
   * caller-provided fallback) and persisting writes. Useful for contexts
   * (e.g. pipeline nodes) where node.params is the sole source of truth and
   * localStorage must not be read from or written to. Default: true.
   */
  enabled?: MaybeRefOrGetter<boolean>
}

/**
 * Persisted model selection — saves to localStorage and restores on next use.
 * @param key localStorage key (e.g. 'transcribe_whisper_model')
 * @param fallback default value if nothing saved
 * @param options optional config; `enabled: false` disables seed + persist
 */
export function usePersistedModel(
  key: string,
  fallback: string = '',
  options?: UsePersistedModelOptions,
) {
  const enabled = () => toValue(options?.enabled ?? true)
  const saved = enabled() ? localStorage.getItem(key) : null
  const value = ref(saved ?? fallback)
  watch(value, (v) => {
    if (v && enabled()) localStorage.setItem(key, v)
  })
  return value
}
