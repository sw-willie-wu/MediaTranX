/* eslint-disable @typescript-eslint/no-explicit-any */
import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useRemoteModelStore } from '@/stores/remoteModels'

vi.mock('@/composables/useApi', () => ({ apiFetch: vi.fn() }))

const toastShow = vi.fn()
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ show: toastShow }) }))

function routeApiFetch(modelsByConn: Record<number, { ok: boolean; models?: any[] }>, conns: any[]) {
  return vi.fn(async (url: string) => {
    if (url === '/setup/remote/connections') {
      return { ok: true, json: async () => ({ connections: conns }) } as unknown as Response
    }
    const m = url.match(/conn_id=(\d+)/)
    const id = m ? Number(m[1]) : -1
    const entry = modelsByConn[id] ?? { ok: false }
    return { ok: entry.ok, json: async () => ({ models: entry.models ?? [] }) } as unknown as Response
  })
}

beforeEach(() => setActivePinia(createPinia()))

describe('fetchAll: parallel + notifyOnError + prune', () => {
  it('does NOT toast on a mutation-path fetch (notifyOnError defaults false)', async () => {
    const { apiFetch } = await import('@/composables/useApi')
    vi.mocked(apiFetch).mockImplementation(routeApiFetch(
      { 2: { ok: true, models: [{ id: 'a', name: 'A' }] }, 4: { ok: false } },
      [{ id: 2, provider: 'openai', name: 'gpt', enabled: true },
       { id: 4, provider: 'ollama', name: 'oll', enabled: true }],
    ))
    toastShow.mockClear()
    const store = useRemoteModelStore()
    await store.fetchAll()
    expect(store.connError[4]).toBe(true)
    expect(toastShow).not.toHaveBeenCalled()
  })

  it('toasts a single aggregated warning when notifyOnError is true', async () => {
    const { apiFetch } = await import('@/composables/useApi')
    vi.mocked(apiFetch).mockImplementation(routeApiFetch(
      { 2: { ok: true, models: [{ id: 'a', name: 'A' }] }, 4: { ok: false } },
      [{ id: 2, provider: 'openai', name: 'gpt', enabled: true },
       { id: 4, provider: 'ollama', name: 'oll', enabled: true }],
    ))
    toastShow.mockClear()
    const store = useRemoteModelStore()
    await store.fetchAll({ notifyOnError: true })
    expect(toastShow).toHaveBeenCalledTimes(1)
    expect(toastShow.mock.calls[0][1]).toMatchObject({ type: 'warning' })
  })

  it('prunes connError for connections no longer present', async () => {
    const { apiFetch } = await import('@/composables/useApi')
    const store = useRemoteModelStore()
    store.connError[99] = true
    vi.mocked(apiFetch).mockImplementation(routeApiFetch(
      { 2: { ok: true, models: [] } },
      [{ id: 2, provider: 'openai', name: 'gpt', enabled: true }],
    ))
    await store.fetchAll({ notifyOnError: true })
    expect(store.connError[99]).toBeUndefined()
  })
})

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

describe('ensureLoaded: cache + in-flight dedup', () => {
  it('fetches once, then serves cache on the second call', async () => {
    const { apiFetch } = await import('@/composables/useApi')
    const fetchMock = routeApiFetch({ 2: { ok: true, models: [] } },
      [{ id: 2, provider: 'openai', name: 'gpt', enabled: true }])
    vi.mocked(apiFetch).mockImplementation(fetchMock)
    const store = useRemoteModelStore()

    await store.ensureLoaded()
    await store.ensureLoaded()    // loaded=true → no network
    const connCalls = fetchMock.mock.calls.filter(c => c[0] === '/setup/remote/connections')
    expect(connCalls).toHaveLength(1)
  })

  it('dedups two concurrent ensureLoaded calls into one fetch', async () => {
    const { apiFetch } = await import('@/composables/useApi')
    const fetchMock = routeApiFetch({ 2: { ok: true, models: [] } },
      [{ id: 2, provider: 'openai', name: 'gpt', enabled: true }])
    vi.mocked(apiFetch).mockImplementation(fetchMock)
    const store = useRemoteModelStore()

    await Promise.all([store.ensureLoaded(), store.ensureLoaded()])
    const connCalls = fetchMock.mock.calls.filter(c => c[0] === '/setup/remote/connections')
    expect(connCalls).toHaveLength(1)
  })
})
