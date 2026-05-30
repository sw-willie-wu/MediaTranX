import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const apiFetch = vi.fn()
vi.mock('@/composables/useApi', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }))

import { useVideoDownloadStore } from '@/stores/videoDownload'

function jsonRes(body: unknown, ok = true) {
  return { ok, json: async () => body } as Response
}

describe('videoDownload store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiFetch.mockReset()
  })

  it('defaults to fail-closed (disabled) before load', () => {
    const s = useVideoDownloadStore()
    expect(s.enabled).toBe(false)
    expect(s.loaded).toBe(false)
  })

  it('load() mirrors backend settings', async () => {
    apiFetch.mockResolvedValueOnce(jsonRes({ agreed: true, enabled: true, quality_mode: 'cap', max_height: 720 }))
    const s = useVideoDownloadStore()
    await s.load()
    expect(s.enabled).toBe(true)
    expect(s.settings.quality_mode).toBe('cap')
    expect(s.loaded).toBe(true)
  })

  it('load() stays disabled on error (fail-closed)', async () => {
    apiFetch.mockRejectedValueOnce(new Error('boom'))
    const s = useVideoDownloadStore()
    await s.load()
    expect(s.enabled).toBe(false)
    expect(s.loaded).toBe(true)
  })

  it('update() PUTs the patch and adopts the response', async () => {
    apiFetch.mockResolvedValueOnce(jsonRes({ agreed: true, enabled: true, quality_mode: 'auto', max_height: 1080 }))
    const s = useVideoDownloadStore()
    await s.update({ agreed: true, enabled: true })
    const [path, init] = apiFetch.mock.calls[0]
    expect(path).toBe('/video/download/settings')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toEqual({ agreed: true, enabled: true })
    expect(s.enabled).toBe(true)
  })
})
