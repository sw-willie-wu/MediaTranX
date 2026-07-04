// frontend/src/stores/__tests__/feedback.test.ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const apiFetchMock = vi.fn()
vi.mock('@/composables/useApi', () => ({ apiFetch: (...a: unknown[]) => apiFetchMock(...a) }))
const showMock = vi.fn()
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ show: showMock }) }))
vi.mock('@/i18n', () => ({ default: { global: { t: (k: string) => k } } }))

import { useFeedbackStore } from '@/stores/feedback'

const SECTIONS = { app_version: '1.0', env_summary: 'env', task_context: '(無)', log_tail: 'log' }

function okJson(data: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => data }
}

beforeEach(() => {
  setActivePinia(createPinia())
  apiFetchMock.mockReset()
  showMock.mockReset()
})

describe('openFeedback 預設', () => {
  it('bug 類型預設勾診斷並抓快照', async () => {
    apiFetchMock.mockResolvedValue(okJson(SECTIONS))
    const s = useFeedbackStore()
    await s.openFeedback({ type: 'bug', taskId: 't-1' })
    expect(s.modalVisible).toBe(true)
    expect(s.includeDiagnostics).toBe(true)
    expect(apiFetchMock).toHaveBeenCalledWith('/feedback/diagnostics?task_id=t-1')
    expect(s.snapshot).toEqual(SECTIONS)
  })

  it('feature 類型預設不勾、不抓', async () => {
    const s = useFeedbackStore()
    await s.openFeedback({ type: 'feature' })
    expect(s.includeDiagnostics).toBe(false)
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})

describe('checkbox 跟隨類型', () => {
  it('未手動動過 → 切類型跟隨預設', async () => {
    apiFetchMock.mockResolvedValue(okJson(SECTIONS))
    const s = useFeedbackStore()
    await s.openFeedback({ type: 'bug' })
    await s.setType('feature')
    expect(s.includeDiagnostics).toBe(false)
    await s.setType('bug')
    expect(s.includeDiagnostics).toBe(true)
  })

  it('手動動過 → 不再跟隨', async () => {
    apiFetchMock.mockResolvedValue(okJson(SECTIONS))
    const s = useFeedbackStore()
    await s.openFeedback({ type: 'bug' })
    await s.toggleInclude(false)          // 手動取消
    await s.setType('feature')
    await s.setType('bug')
    expect(s.includeDiagnostics).toBe(false)
  })

  it('取消勾選丟棄快照、重新勾選重新 GET 換新快照（spec §3.1）', async () => {
    apiFetchMock.mockResolvedValue(okJson(SECTIONS))
    const s = useFeedbackStore()
    await s.openFeedback({ type: 'bug' })   // 首抓 1 次
    await s.toggleInclude(false)
    expect(s.snapshot).toBeNull()           // 舊快照丟棄
    const before = apiFetchMock.mock.calls.length
    await s.toggleInclude(true)
    expect(apiFetchMock.mock.calls.length).toBe(before + 1)   // 重新 GET
    expect(s.snapshot).toEqual(SECTIONS)
  })
})

describe('submit', () => {
  it('空描述不送', async () => {
    const s = useFeedbackStore()
    await s.openFeedback({ type: 'other' })
    s.form.description = '   '
    await s.submit()
    expect(apiFetchMock).not.toHaveBeenCalledWith('/feedback', expect.anything())
  })

  it('204 → success toast + 關 modal', async () => {
    apiFetchMock.mockResolvedValue({ ok: true, status: 204, json: async () => ({}) })
    const s = useFeedbackStore()
    await s.openFeedback({ type: 'other' })   // 不勾診斷
    s.form.description = 'hi'
    await s.submit()
    const [path, init] = apiFetchMock.mock.calls.at(-1)!
    expect(path).toBe('/feedback')
    const body = JSON.parse((init as RequestInit).body as string)
    expect(body).toMatchObject({ type: 'other', description: 'hi', include_diagnostics: false })
    expect(body.diagnostics).toBeUndefined()
    expect(s.modalVisible).toBe(false)
    expect(showMock).toHaveBeenCalledWith('feedback.success', expect.objectContaining({ type: 'success' }))
  })

  it('勾診斷 → body 帶快照原樣', async () => {
    apiFetchMock.mockResolvedValueOnce(okJson(SECTIONS))                       // GET
    apiFetchMock.mockResolvedValueOnce({ ok: true, status: 204, json: async () => ({}) })  // POST
    const s = useFeedbackStore()
    await s.openFeedback({ type: 'bug' })
    s.form.description = 'x'
    await s.submit()
    const body = JSON.parse((apiFetchMock.mock.calls.at(-1)![1] as RequestInit).body as string)
    expect(body.diagnostics).toEqual(SECTIONS)
  })

  it('勾診斷但無快照 → 先重試 GET 一次，仍失敗 → toast + 自動取消勾選、不 POST', async () => {
    apiFetchMock.mockRejectedValue(new Error('net'))
    const s = useFeedbackStore()
    await s.openFeedback({ type: 'bug' })     // 首抓失敗 → snapshot null
    s.form.description = 'x'
    apiFetchMock.mockClear()
    apiFetchMock.mockRejectedValue(new Error('net'))
    await s.submit()
    expect(apiFetchMock).toHaveBeenCalledTimes(1)             // 只重試 GET，一次
    expect(String(apiFetchMock.mock.calls[0][0])).toContain('/feedback/diagnostics')
    expect(s.includeDiagnostics).toBe(false)                  // 自動取消勾選
    expect(s.modalVisible).toBe(true)                         // modal 不關
  })

  it('失敗 502 → error toast 帶「改用瀏覽器回報」action，modal 不關內容保留', async () => {
    apiFetchMock.mockResolvedValue(okJson({ error_code: 'form_network_error', detail: 'x',
      prefill_url: 'https://docs.google.com/forms/x' }, 502))
    const s = useFeedbackStore()
    await s.openFeedback({ type: 'other' })
    s.form.description = 'keep me'
    await s.submit()
    expect(s.modalVisible).toBe(true)
    expect(s.form.description).toBe('keep me')
    const opts = showMock.mock.calls.at(-1)![1]
    expect(opts.type).toBe('error')
    expect(opts.action.label).toBe('feedback.use_browser')
    // action callback 開外部瀏覽器
    const openExternal = vi.fn()
    ;(window as any).electron = { openExternal }
    opts.action.callback()
    expect(openExternal).toHaveBeenCalledWith('https://docs.google.com/forms/x')
  })
})
