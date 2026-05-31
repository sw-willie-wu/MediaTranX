/* eslint-disable @typescript-eslint/no-explicit-any */
import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useRemoteModelStore } from '@/stores/remoteModels'

vi.mock('@/composables/useApi', () => ({ apiFetch: vi.fn() }))

beforeEach(() => setActivePinia(createPinia()))

describe('fetchConnModels failure handling', () => {
  it('marks connError and drops the cache entry on a non-ok response', async () => {
    const { apiFetch } = await import('@/composables/useApi')
    vi.mocked(apiFetch).mockResolvedValueOnce({ ok: false, json: async () => ({}) } as unknown as Response)
    const store = useRemoteModelStore()
    await store.fetchConnModels({ id: 4 })
    expect(store.connError[4]).toBe(true)
    expect(store.connModels[4]).toBeUndefined()  // not [] — so next fetchAll retries
  })

  it('clears connError and caches models on success', async () => {
    const { apiFetch } = await import('@/composables/useApi')
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true, json: async () => ({ models: [{ id: 'm1', name: 'M1' }] }),
    } as unknown as Response)
    const store = useRemoteModelStore()
    await store.fetchConnModels({ id: 2 })
    expect(store.connError[2]).toBe(false)
    expect(store.connModels[2]).toHaveLength(1)
  })
})
