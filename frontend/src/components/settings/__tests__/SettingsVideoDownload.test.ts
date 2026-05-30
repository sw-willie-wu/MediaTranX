import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

const apiFetch = vi.fn()
vi.mock('@/composables/useApi', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }))
// The component builds AppSelect option labels via useI18n() in <script setup>.
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))

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
    // AppToggle marks the disabled state with the `is-disabled` class (no
    // native `disabled` attribute on its <label> root).
    const enable = w.find('[data-test="vd-enable"]')
    expect(enable.classes()).toContain('is-disabled')
  })

  it('agreeing PUTs agreed=true', async () => {
    const w = mount(SettingsVideoDownload, mountOpts)
    await flushPromises()
    apiFetch.mockResolvedValueOnce(jsonRes({ agreed: true, enabled: false, quality_mode: 'auto', max_height: 1080 }))
    // AppToggle flips on click (it has no checkbox input to setValue on).
    await w.find('[data-test="vd-agree"]').trigger('click')
    await flushPromises()
    const putCall = apiFetch.mock.calls.find((c) => c[1]?.method === 'PUT')
    expect(putCall).toBeTruthy()
    expect(JSON.parse(putCall![1].body).agreed).toBe(true)
  })
})
