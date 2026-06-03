import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useComputeSettingsStore } from '@/stores/computeSettings'

vi.mock('@/composables/useApi', () => ({
  apiFetch: vi.fn(),
}))
import { apiFetch } from '@/composables/useApi'

describe('computeSettings store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('loads allow_cpu_fallback from backend', async () => {
    ;(apiFetch as any).mockResolvedValue({ ok: true, json: async () => ({ allow_cpu_fallback: false }) })
    const store = useComputeSettingsStore()
    await store.load()
    expect(store.settings.allow_cpu_fallback).toBe(false)
  })

  it('update PUTs patch and stores response', async () => {
    ;(apiFetch as any).mockResolvedValue({ ok: true, json: async () => ({ allow_cpu_fallback: true }) })
    const store = useComputeSettingsStore()
    await store.update({ allow_cpu_fallback: true })
    expect(apiFetch).toHaveBeenCalledWith('/setup/config/compute', expect.objectContaining({ method: 'PUT' }))
    expect(store.settings.allow_cpu_fallback).toBe(true)
  })
})
