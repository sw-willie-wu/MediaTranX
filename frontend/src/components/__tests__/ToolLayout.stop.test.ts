import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('vue-i18n', async (orig) => {
  const mod = await orig<typeof import('vue-i18n')>()
  return { ...mod, useI18n: () => ({ t: (k: string) => k }) }
})
vi.mock('@/composables/useTitlebar', () => ({ useTitlebar: () => ({ setFileName: vi.fn(), clearFileName: vi.fn() }) }))
vi.mock('@/composables/usePasteUpload', () => ({ usePasteUpload: vi.fn() }))
vi.mock('@/composables/useUrlDownload', () => ({ useUrlDownload: () => ({ handlePastedUrl: vi.fn() }) }))
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ show: vi.fn() }) }))

import ToolLayout from '@/components/ToolLayout.vue'

function mountLayout(props: Record<string, unknown> = {}): VueWrapper {
  return mount(ToolLayout, {
    props: {
      title: 'T',
      subFunctions: [{ id: 'fn', name: 'Fn', icon: 'bi-x' }],
      currentFunction: 'fn',
      ...props,
    },
    global: {
      mocks: { $t: (k: string) => k },
      stubs: {
        AppThreePaneLayout: { template: '<div><slot name="left" /><slot name="center" /><slot name="right" /></div>' },
        AppUploadZone: true,
        ComparisonSlider: true,
        UnsupportedFileOverlay: true,
      },
    },
  })
}

const btn = (w: VueWrapper) => w.find('.execute-btn')

beforeEach(() => setActivePinia(createPinia()))

describe('ToolLayout — 停止按鈕三態', () => {
  it('idle：點擊 emit execute；executeDisabled 時 disabled', async () => {
    const w = mountLayout()
    await btn(w).trigger('click')
    expect(w.emitted('execute')).toHaveLength(1)
    expect(w.emitted('stop')).toBeUndefined()

    const w2 = mountLayout({ executeDisabled: true })
    expect((btn(w2).element as HTMLButtonElement).disabled).toBe(true)
  })

  it('executing：紅色停止、可點、emit stop（executeDisabled 不影響）', async () => {
    const w = mountLayout({ executeLoading: true, executeDisabled: true })
    expect(btn(w).classes()).toContain('is-stop')
    expect((btn(w).element as HTMLButtonElement).disabled).toBe(false)
    expect(btn(w).text()).toContain('common.stop')
    expect(btn(w).find('i.bi-stop-fill').exists()).toBe(true)
    await btn(w).trigger('click')
    expect(w.emitted('stop')).toHaveLength(1)
    expect(w.emitted('execute')).toBeUndefined()
  })

  it('canceling：disabled + spinner + 取消中', () => {
    const w = mountLayout({ executeLoading: true, executeCanceling: true })
    expect((btn(w).element as HTMLButtonElement).disabled).toBe(true)
    expect(btn(w).text()).toContain('common.canceling')
    expect(btn(w).find('.spinner-border').exists()).toBe(true)
    expect(btn(w).classes()).not.toContain('is-stop')
  })

  it('正常完成（無取消）仍閃 success flash', async () => {
    const w = mountLayout({ executeLoading: true, hasResult: true })
    await w.setProps({ executeLoading: false })
    expect(btn(w).classes()).toContain('is-success')
    expect(btn(w).text()).toContain('common.completed')
  })

  it('取消結束不閃 success flash（同 tick 一起翻 false）', async () => {
    const w = mountLayout({ executeLoading: true, hasResult: true })
    await w.setProps({ executeCanceling: true })                         // latch 設起（早一個 flush）
    await w.setProps({ executeCanceling: false, executeLoading: false }) // 同 tick collapse
    expect(btn(w).classes()).not.toContain('is-success')
  })

  it('latch 跨邊緣：批次取消中 active 切換不清 latch；下次執行才重置', async () => {
    const w = mountLayout({ executeLoading: true, hasResult: true })
    await w.setProps({ executeCanceling: true })          // 停止確認後
    await w.setProps({ executeLoading: false })           // active entry 先收斂 → 邊緣 1：抑制
    expect(btn(w).classes()).not.toContain('is-success')
    await w.setProps({ executeLoading: true })            // 切 active 到仍 canceling 的 entry（不得清 latch）
    await w.setProps({ executeCanceling: false, executeLoading: false }) // 該 entry 收斂 → 邊緣 2
    expect(btn(w).classes()).not.toContain('is-success')  // 仍抑制

    await btn(w).trigger('click')                         // idle → emit execute → latch 重置
    expect(w.emitted('execute')).toHaveLength(1)
    await w.setProps({ executeLoading: true })
    await w.setProps({ executeLoading: false })           // 正常完成
    expect(btn(w).classes()).toContain('is-success')      // flash 恢復
  })
})
