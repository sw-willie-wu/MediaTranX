import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useRemoteModelStore } from '@/stores/remoteModels'

vi.mock('@/composables/useApi', () => ({
  apiFetch: vi.fn(async () => ({ ok: true, json: async () => ({ api_key: 'sk-REVEALED' }) })),
}))

beforeEach(() => setActivePinia(createPinia()))

describe('remoteModelStore.revealKey', () => {
  it('revealKey POSTs and returns the plaintext without storing it', async () => {
    const store = useRemoteModelStore()
    const key = await store.revealKey(3)
    expect(key).toBe('sk-REVEALED')
    // never persisted into the reactive connections array
    expect(JSON.stringify(store.connections)).not.toContain('sk-REVEALED')
  })

  it('returns null when the response is not ok', async () => {
    const { apiFetch } = await import('@/composables/useApi')
    vi.mocked(apiFetch).mockResolvedValueOnce({ ok: false, json: async () => ({}) } as unknown as Response)
    const store = useRemoteModelStore()
    const key = await store.revealKey(3)
    expect(key).toBeNull()
  })

  it('returns null when api_key is absent in the response body', async () => {
    const { apiFetch } = await import('@/composables/useApi')
    vi.mocked(apiFetch).mockResolvedValueOnce({ ok: true, json: async () => ({}) } as unknown as Response)
    const store = useRemoteModelStore()
    const key = await store.revealKey(3)
    expect(key).toBeNull()
  })
})
