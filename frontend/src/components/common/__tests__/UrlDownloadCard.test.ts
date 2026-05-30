import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

import UrlDownloadCard from '@/components/common/UrlDownloadCard.vue'
import { useUrlDownload } from '@/composables/useUrlDownload'

const mountOpts = { global: { mocks: { $t: (k: string) => k } } }

describe('UrlDownloadCard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useUrlDownload().cancel()
  })

  it('renders nothing when not visible', () => {
    const w = mount(UrlDownloadCard, mountOpts)
    expect(w.find('.url-download-card').exists()).toBe(false)
  })

  it('shows loading state while probing', () => {
    const u = useUrlDownload()
    u.visible.value = true
    u.loading.value = true
    const w = mount(UrlDownloadCard, mountOpts)
    expect(w.find('.udc-loading').exists()).toBe(true)
  })

  it('shows the error reason when not downloadable', () => {
    const u = useUrlDownload()
    u.visible.value = true
    u.loading.value = false
    u.error.value = 'private'
    const w = mount(UrlDownloadCard, mountOpts)
    expect(w.find('.udc-error').exists()).toBe(true)
    expect(w.text()).toContain('video_download.reason.private')
  })

  it('shows title + download button when downloadable', () => {
    const u = useUrlDownload()
    u.visible.value = true
    u.loading.value = false
    u.probe.value = {
      downloadable: true, title: 'My Clip', duration: 90, uploader: 'U',
      thumbnail: '', formats: [], reason: '',
    }
    const w = mount(UrlDownloadCard, mountOpts)
    expect(w.text()).toContain('My Clip')
    expect(w.find('.udc-download-btn').exists()).toBe(true)
  })
})
