import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/composables/useApi', () => ({ apiFetch: vi.fn() }))
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ show: vi.fn() }) }))
vi.mock('vue-i18n', async (orig) => {
  const mod = await orig<typeof import('vue-i18n')>()
  return { ...mod, useI18n: () => ({ t: (k: string) => k }) }
})
vi.mock('@/i18n', () => ({ default: { global: { t: (k: string) => k } } }))

import FeedbackModal from '@/components/FeedbackModal.vue'
import { useFeedbackStore } from '@/stores/feedback'

const SECTIONS = { app_version: '1.0', env_summary: 'ENV-TEXT', task_context: 'CTX', log_tail: 'LOG' }

function mountModal() {
  return mount(FeedbackModal, { global: { stubs: { teleport: true, Teleport: true } } })
}

beforeEach(() => setActivePinia(createPinia()))

describe('FeedbackModal', () => {
  it('modalVisible=false 時不渲染', () => {
    const w = mountModal()
    expect(w.find('.feedback-modal').exists()).toBe(false)
  })

  it('開啟後渲染三個類型選項與描述欄', async () => {
    const s = useFeedbackStore()
    s.modalVisible = true
    const w = mountModal()
    await w.vm.$nextTick()
    expect(w.findAll('input[type="radio"]').length).toBe(3)
    expect(w.find('textarea').exists()).toBe(true)
  })

  it('空描述時送出鈕 disabled', async () => {
    const s = useFeedbackStore()
    s.modalVisible = true
    s.form.description = ''
    const w = mountModal()
    await w.vm.$nextTick()
    expect((w.find('button.submit-btn').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('預覽展開時顯示快照四節內容', async () => {
    const s = useFeedbackStore()
    s.modalVisible = true
    s.includeDiagnostics = true
    s.snapshot = SECTIONS
    const w = mountModal()
    await w.vm.$nextTick()
    await w.find('.preview-toggle').trigger('click')
    expect(w.text()).toContain('ENV-TEXT')
    expect(w.text()).toContain('LOG')
  })

  it('快照抓取失敗顯示錯誤狀態', async () => {
    const s = useFeedbackStore()
    s.modalVisible = true
    s.includeDiagnostics = true
    s.snapshotError = true
    const w = mountModal()
    await w.vm.$nextTick()
    await w.find('.preview-toggle').trigger('click')
    expect(w.text()).toContain('feedback.diag_fetch_failed')
  })
})
