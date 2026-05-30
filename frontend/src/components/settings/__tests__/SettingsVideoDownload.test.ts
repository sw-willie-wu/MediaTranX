import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

const apiFetch = vi.fn()
vi.mock('@/composables/useApi', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }))

import SettingsVideoDownload from '@/components/settings/SettingsVideoDownload.vue'

const mountOpts = { global: { mocks: { $t: (k: string) => k } } }

function jsonRes(body: unknown, ok = true) {
  return { ok, json: async () => body } as Response
}

describe('SettingsVideoDownload', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiFetch.mockReset()
    apiFetch.mockResolvedValue(jsonRes({ agreed: false, enabled: false, quality_mode: 'auto', max_height: 1080 }))
  })

  it('disables the enable toggle until terms are agreed', async () => {
    const w = mount(SettingsVideoDownload, mountOpts)
    await flushPromises()
    const enable = w.find('[data-test="vd-enable"]')
    expect(enable.attributes('disabled')).toBeDefined()
  })

  it('agreeing PUTs agreed=true', async () => {
    const w = mount(SettingsVideoDownload, mountOpts)
    await flushPromises()
    apiFetch.mockResolvedValueOnce(jsonRes({ agreed: true, enabled: false, quality_mode: 'auto', max_height: 1080 }))
    await w.find('[data-test="vd-agree"]').setValue(true)
    await flushPromises()
    const putCall = apiFetch.mock.calls.find((c) => c[1]?.method === 'PUT')
    expect(putCall).toBeTruthy()
    expect(JSON.parse(putCall![1].body).agreed).toBe(true)
  })
})
