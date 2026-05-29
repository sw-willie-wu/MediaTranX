import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { defineComponent, h, KeepAlive } from 'vue'
import { mount } from '@vue/test-utils'
import { usePendingFileListener } from '@/composables/usePendingFileListener'
import { useFilesStore } from '@/stores/files'

describe('usePendingFileListener — existing-results event', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('dispatching pending-results-ready consumes refs into handleExistingFiles', async () => {
    const handleExisting = vi.fn()
    const Child = defineComponent({
      setup() {
        usePendingFileListener(() => {}, undefined, handleExisting)
        return () => h('div')
      },
    })
    // KeepAlive so onActivated fires
    const Wrapper = defineComponent({ render: () => h(KeepAlive, null, { default: () => h(Child) }) })
    mount(Wrapper)
    await Promise.resolve()

    const s = useFilesStore()
    s.setPendingResults([{ fileId: 'a', filename: 'a.mp4', fileSize: 1, mimeType: 'video/mp4' }])
    window.dispatchEvent(new CustomEvent('pending-results-ready'))
    await Promise.resolve()

    expect(handleExisting).toHaveBeenCalledOnce()
    expect(handleExisting.mock.calls[0][0]).toHaveLength(1)
  })
})
