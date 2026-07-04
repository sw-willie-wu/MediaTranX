// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import UpdateModal from '@/components/UpdateModal.vue'
import { useUpdateStore } from '@/stores/update'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      settings: {
        general: {
          update: {
            found: 'New version v{version} available. Update?',
            cancel: 'Cancel',
            download_only: 'Download only',
            download_install: 'Download & install',
            downloading: 'Downloading {percent}%',
            download_failed: 'Download failed',
            install_failed: 'Failed to launch the installer',
          },
        },
      },
    },
  },
})

function mountModal() {
  return mount(UpdateModal, { global: { plugins: [i18n], stubs: { Teleport: true, Transition: false } } })
}

beforeEach(() => setActivePinia(createPinia()))

describe('UpdateModal', () => {
  it('is hidden when modalVisible is false', () => {
    const w = mountModal()
    expect(w.find('.update-dialog').exists()).toBe(false)
  })

  it('shows the found message and three action buttons', async () => {
    const store = useUpdateStore()
    store.modalVisible = true
    store.latest = '1.6.0'
    const w = mountModal()
    await w.vm.$nextTick()
    expect(w.text()).toContain('New version v1.6.0')
    const btns = w.findAll('.update-btn')
    expect(btns.map((b) => b.text())).toEqual(['Cancel', 'Download only', 'Download & install'])
  })

  it('cancel button dismisses the modal', async () => {
    const store = useUpdateStore()
    store.modalVisible = true
    const spy = vi.spyOn(store, 'dismissModal')
    const w = mountModal()
    await w.find('.update-btn.cancel').trigger('click')
    expect(spy).toHaveBeenCalledOnce()
  })

  it("'download only' and 'download & install' dispatch the right action", async () => {
    const store = useUpdateStore()
    store.modalVisible = true
    const spy = vi.spyOn(store, 'download').mockResolvedValue(undefined)
    const w = mountModal()
    await w.find('.update-btn.secondary').trigger('click')
    expect(spy).toHaveBeenCalledWith('only')
    await w.find('.update-btn.primary').trigger('click')
    expect(spy).toHaveBeenCalledWith('install')
  })

  it('shows an inline error above the buttons on failure (buttons still available to retry)', async () => {
    const store = useUpdateStore()
    store.modalVisible = true
    store.lastError = 'network'
    const w = mountModal()
    await w.vm.$nextTick()
    expect(w.find('.update-error').text()).toContain('Download failed')
    // buttons remain so the user can retry or cancel
    expect(w.findAll('.update-btn').length).toBe(3)
  })

  it('shows the progress bar (not buttons) while downloading', async () => {
    const store = useUpdateStore()
    store.modalVisible = true
    store.downloading = true
    store.downloadPercent = 42
    const w = mountModal()
    await w.vm.$nextTick()
    expect(w.find('.update-actions').exists()).toBe(false)
    expect(w.find('.update-fill').attributes('style')).toContain('42%')
    expect(w.text()).toContain('Downloading 42%')
  })
})
