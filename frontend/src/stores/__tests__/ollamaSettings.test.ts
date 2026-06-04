import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useOllamaSettingsStore } from '@/stores/ollamaSettings'

vi.mock('@/composables/useApi', () => ({
  apiFetch: vi.fn(),
}))
import { apiFetch } from '@/composables/useApi'

describe('ollamaSettings store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('defaults num_ctx cap to 8192', () => {
    const store = useOllamaSettingsStore()
    expect(store.settings.ollama_num_ctx_cap).toBe(8192)
  })

  it('loads ollama_num_ctx_cap from backend', async () => {
    ;(apiFetch as any).mockResolvedValue({ ok: true, json: async () => ({ ollama_num_ctx_cap: 16384 }) })
    const store = useOllamaSettingsStore()
    await store.load()
    expect(store.settings.ollama_num_ctx_cap).toBe(16384)
  })

  it('update PUTs patch and stores response', async () => {
    ;(apiFetch as any).mockResolvedValue({ ok: true, json: async () => ({ ollama_num_ctx_cap: 32768 }) })
    const store = useOllamaSettingsStore()
    await store.update({ ollama_num_ctx_cap: 32768 })
    expect(apiFetch).toHaveBeenCalledWith('/setup/config/ollama', expect.objectContaining({ method: 'PUT' }))
    expect(store.settings.ollama_num_ctx_cap).toBe(32768)
  })
})
