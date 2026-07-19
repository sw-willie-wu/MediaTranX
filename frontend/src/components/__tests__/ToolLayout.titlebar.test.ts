import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, KeepAlive, ref } from 'vue'
import { setActivePinia, createPinia } from 'pinia'

// 模組級捕捉 setFileName/clearFileName——驗證 KeepAlive re-activate 時 titlebar 被正確重設
const setFileName = vi.fn()
const clearFileName = vi.fn()

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('vue-i18n', async (orig) => {
  const mod = await orig<typeof import('vue-i18n')>()
  return { ...mod, useI18n: () => ({ t: (k: string) => k }) }
})
vi.mock('@/composables/useTitlebar', () => ({ useTitlebar: () => ({ setFileName, clearFileName }) }))
vi.mock('@/composables/usePasteUpload', () => ({ usePasteUpload: vi.fn() }))
vi.mock('@/composables/useUrlDownload', () => ({ useUrlDownload: () => ({ handlePastedUrl: vi.fn() }) }))
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ show: vi.fn() }) }))

import ToolLayout from '@/components/ToolLayout.vue'

const STUBS = {
  AppThreePaneLayout: { template: '<div><slot name="left" /><slot name="center" /><slot name="right" /></div>' },
  AppUploadZone: true,
  ComparisonSlider: true,
  UnsupportedFileOverlay: true,
}

/** 用 KeepAlive 包 ToolLayout，show 切換觸發 deactivate/activate。 */
function mountKeepAlive(activeFileName: string) {
  const show = ref(true)
  const wrapper = mount(
    defineComponent({
      setup() {
        return () =>
          h(KeepAlive, null, {
            default: () =>
              show.value
                ? h(ToolLayout, {
                    title: 'T',
                    subFunctions: [{ id: 'fn', name: 'Fn', icon: 'bi-x' }],
                    currentFunction: 'fn',
                    activeFileName,
                  })
                : null,
          })
      },
    }),
    { global: { mocks: { $t: (k: string) => k }, stubs: STUBS } },
  )
  return { wrapper, show }
}

beforeEach(() => {
  setActivePinia(createPinia())
  setFileName.mockClear()
  clearFileName.mockClear()
})

describe('ToolLayout titlebar — KeepAlive re-activate 重設', () => {
  it('掛載時以 activeFileName 設定 titlebar', () => {
    mountKeepAlive('a.mp4')
    expect(setFileName).toHaveBeenCalledWith('a.mp4')
  })

  it('deactivate 後 activate → 以同 activeFileName re-assert（不因來源未變而殘留）', async () => {
    const { show, wrapper } = mountKeepAlive('a.mp4')
    setFileName.mockClear()
    show.value = false // deactivate
    await wrapper.vm.$nextTick()
    show.value = true // activate → onActivated re-assert
    await wrapper.vm.$nextTick()
    expect(setFileName).toHaveBeenCalledWith('a.mp4')
  })

  it('空 activeFileName 的 view activate → clearFileName（不是 setFileName("")）', async () => {
    const { show, wrapper } = mountKeepAlive('')
    clearFileName.mockClear()
    setFileName.mockClear()
    show.value = false
    await wrapper.vm.$nextTick()
    show.value = true
    await wrapper.vm.$nextTick()
    expect(clearFileName).toHaveBeenCalled()
    expect(setFileName).not.toHaveBeenCalledWith('')
  })
})
