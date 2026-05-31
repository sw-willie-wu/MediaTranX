// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import ChatHeader from '@/components/agent/ChatHeader.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      agent: {
        bubble: { title: 'Agent Chat', token_count: 'in: {prompt} / out: {completion}' },
        session: { back: 'Back to conversations' },
      },
    },
  },
})

beforeEach(() => setActivePinia(createPinia()))

describe('ChatHeader', () => {
  it('emits back when the back button is clicked', async () => {
    const w = mount(ChatHeader, {
      props: { tokenUsage: { prompt: 0, completion: 0 } },
      global: { plugins: [i18n] },
    })
    await w.find('.header-back-btn').trigger('click')
    expect(w.emitted('back')).toBeTruthy()
  })

  it('does NOT render a trash/clear button', () => {
    const w = mount(ChatHeader, {
      props: { tokenUsage: { prompt: 0, completion: 0 } },
      global: { plugins: [i18n] },
    })
    expect(w.find('.bi-trash3').exists()).toBe(false)
  })

  it('shows token counter when usage > 0', () => {
    const w = mount(ChatHeader, {
      props: { tokenUsage: { prompt: 5, completion: 3 } },
      global: { plugins: [i18n] },
    })
    expect(w.text()).toContain('in: 5 / out: 3')
  })
})
