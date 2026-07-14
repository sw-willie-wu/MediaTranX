// @vitest-environment jsdom
/**
 * 分頁列元件——切頁/新增/關閉確認/雙擊改名（spec §3）。
 * useConfirm mock 成可控 promise；store 用真 pinia（runner 不會被觸發）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'

const confirmMock = vi.fn(async () => true)
vi.mock('@/composables/useConfirm', () => ({
  useConfirm: () => ({ confirm: confirmMock }),
}))

import PipelineTabBar from '@/components/pipeline/PipelineTabBar.vue'
import { usePipelineStore } from '@/stores/pipeline'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      pipeline: {
        titlebar_unnamed: 'Untitled',
        tab_new: 'New tab',
        tab_close: 'Close tab',
        tab_close_confirm: 'Unsaved changes will be lost. Close this tab?',
        tab_running_no_close: 'Running — stop it first',
        tab_limit: 'Tab limit reached',
      },
    },
  },
})

function mountBar() {
  return mount(PipelineTabBar, { global: { plugins: [i18n] } })
}

beforeEach(() => {
  setActivePinia(createPinia())
  confirmMock.mockClear()
  confirmMock.mockResolvedValue(true)
})

describe('PipelineTabBar', () => {
  it('渲染 tabs、active 樣式、空名顯示 Untitled', () => {
    const store = usePipelineStore()
    store.renameDoc(store.tabs[0].id, '')
    const w = mountBar()
    expect(w.findAll('.pipeline-tab')).toHaveLength(1)
    expect(w.find('.pipeline-tab').classes()).toContain('is-active')
    expect(w.find('.tab-name').text()).toBe('Untitled')
  })

  it('點 tab 切 activeDocId', async () => {
    const store = usePipelineStore()
    const first = store.tabs[0].id
    store.newDoc()
    const w = mountBar()
    await w.findAll('.pipeline-tab')[0].trigger('click')
    expect(store.activeDocId).toBe(first)
  })

  it('＋ 開新分頁；滿 8 頁 disabled', async () => {
    const store = usePipelineStore()
    const w = mountBar()
    await w.find('.tab-add').trigger('click')
    expect(store.tabs).toHaveLength(2)
    while (store.tabs.length < 8) store.newDoc()
    await w.vm.$nextTick()
    expect(w.find('.tab-add').attributes('disabled')).toBeDefined()
  })

  it('關空白分頁不確認直接關', async () => {
    const store = usePipelineStore()
    store.newDoc()
    const w = mountBar()
    await w.findAll('.tab-close')[1].trigger('click')
    expect(confirmMock).not.toHaveBeenCalled()
    expect(store.tabs).toHaveLength(1)
  })

  it('關非空分頁先確認：true 關、false 留', async () => {
    const store = usePipelineStore()
    store.addToolNode('video.cut', { x: 0, y: 0 })
    store.newDoc()
    const w = mountBar()

    confirmMock.mockResolvedValueOnce(false)
    await w.findAll('.tab-close')[0].trigger('click')
    await w.vm.$nextTick()
    expect(confirmMock).toHaveBeenCalledTimes(1)
    expect(store.tabs).toHaveLength(2)

    confirmMock.mockResolvedValueOnce(true)
    await w.findAll('.tab-close')[0].trigger('click')
    await vi.waitFor(() => expect(store.tabs).toHaveLength(1))
  })

  it('雙擊改名：Enter 提交、Esc 取消', async () => {
    const store = usePipelineStore()
    const id = store.tabs[0].id
    store.renameDoc(id, 'old')
    const w = mountBar()

    await w.find('.pipeline-tab').trigger('dblclick')
    const input = w.find('.tab-rename')
    expect(input.exists()).toBe(true)
    await input.setValue('新名字')
    await input.trigger('keydown.enter')
    expect(store.tabs[0].name).toBe('新名字')

    await w.find('.pipeline-tab').trigger('dblclick')
    await w.find('.tab-rename').setValue('不要這個')
    await w.find('.tab-rename').trigger('keydown.esc')
    expect(store.tabs[0].name).toBe('新名字')
  })
})
