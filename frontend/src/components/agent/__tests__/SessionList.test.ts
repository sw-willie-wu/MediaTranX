// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

// --- mocks (declared before importing the component) ---
const apiFetchMock = vi.fn()
vi.mock('@/composables/useApi', () => ({
  getApiBase: () => '/api',
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
}))

const deleteSessionMock = vi.fn(() => Promise.resolve())
vi.mock('@/composables/useAgent', () => ({
  useAgent: () => ({ deleteSession: deleteSessionMock }),
}))

const showMock = vi.fn()
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ show: showMock }),
}))

import SessionList from '@/components/agent/SessionList.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      agent: {
        bubble: { empty: 'No messages yet' },
        session: {
          new_chat: '+ New chat',
          empty: 'No conversations yet',
          delete: 'Delete conversation',
          delete_confirm: 'Delete this conversation?',
          load_failed: 'Failed to load conversations',
          delete_failed: 'Failed to delete conversation',
          time: { just_now: 'just now', minutes_ago: '{n}m ago', hours_ago: '{n}h ago', days_ago: '{n}d ago' },
        },
      },
    },
  },
})

function mountList() {
  return mount(SessionList, { global: { plugins: [i18n] } })
}

beforeEach(() => {
  apiFetchMock.mockReset()
  deleteSessionMock.mockClear()
  showMock.mockClear()
})

describe('SessionList', () => {
  it('fetches and renders session rows with preview', async () => {
    apiFetchMock.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([
        { id: 's1', last_preview: 'hello world', updated_at: new Date().toISOString(), message_count: 2 },
      ]),
    })
    const w = mountList()
    await flushPromises()
    expect(w.text()).toContain('hello world')
    expect(apiFetchMock).toHaveBeenCalledWith('/agent/sessions')
  })

  it('shows empty state when no sessions', async () => {
    apiFetchMock.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve([]) })
    const w = mountList()
    await flushPromises()
    expect(w.text()).toContain('No conversations yet')
  })

  it('emits new-chat when the + button is clicked', async () => {
    apiFetchMock.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve([]) })
    const w = mountList()
    await flushPromises()
    await w.find('.session-new-btn').trigger('click')
    expect(w.emitted('new-chat')).toBeTruthy()
  })

  it('emits select with the session id on row click', async () => {
    apiFetchMock.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([
        { id: 's1', last_preview: 'hi', updated_at: new Date().toISOString(), message_count: 1 },
      ]),
    })
    const w = mountList()
    await flushPromises()
    await w.find('.session-row-main').trigger('click')
    expect(w.emitted('select')?.[0]).toEqual(['s1'])
  })

  it('deletes a row via the composable after confirm', async () => {
    apiFetchMock
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve([
        { id: 's1', last_preview: 'hi', updated_at: new Date().toISOString(), message_count: 1 },
      ]) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve([]) })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const w = mountList()
    await flushPromises()
    await w.find('.session-delete-btn').trigger('click')
    await flushPromises()
    expect(deleteSessionMock).toHaveBeenCalledWith('s1')
  })

  it('toasts on list fetch failure', async () => {
    apiFetchMock.mockResolvedValueOnce({ ok: false, status: 500 })
    const w = mountList()
    await flushPromises()
    expect(showMock).toHaveBeenCalled()
    expect(w.text()).toContain('No conversations yet')
  })
})
