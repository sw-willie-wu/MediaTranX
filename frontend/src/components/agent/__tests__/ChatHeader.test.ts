// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import ChatHeader from '@/components/agent/ChatHeader.vue'
import { useAgentSettingsStore } from '@/stores/agentSettings'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      agent: {
        bubble: {
          title: 'Agent Chat',
          token_count: 'in: {prompt} / out: {completion}',
          policy_tooltip: 'Confirmation policy: {mode} (click to cycle)',
          policy_short: { standard: 'Standard', full_auto: 'Auto', ask: 'Ask', custom: 'Custom' },
        },
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

  it('shows the full Ollama tag in the model badge (modelId with colon)', () => {
    const store = useAgentSettingsStore()
    store.setModelChoice('remote:ollama:1:gpt-oss:120b')
    const w = mount(ChatHeader, {
      props: { tokenUsage: { prompt: 0, completion: 0 } },
      global: { plugins: [i18n] },
    })
    expect(w.find('.model-badge').text()).toBe('gpt-oss:120b')
  })

  it('shows the trailing model name for a colon-free remote model', () => {
    const store = useAgentSettingsStore()
    store.setModelChoice('remote:openai:1:gpt-4o-mini')
    const w = mount(ChatHeader, {
      props: { tokenUsage: { prompt: 0, completion: 0 } },
      global: { plugins: [i18n] },
    })
    expect(w.find('.model-badge').text()).toBe('gpt-4o-mini')
  })

  it('drops the quant suffix for a local model badge', () => {
    const store = useAgentSettingsStore()
    store.setModelChoice('qwen3:8b:Q4_K_M')
    const w = mount(ChatHeader, {
      props: { tokenUsage: { prompt: 0, completion: 0 } },
      global: { plugins: [i18n] },
    })
    expect(w.find('.model-badge').text()).toBe('qwen3:8b')
  })

  it('renders the policy badge with the current policy short label (default: Standard)', () => {
    const w = mount(ChatHeader, {
      props: { tokenUsage: { prompt: 0, completion: 0 } },
      global: { plugins: [i18n] },
    })
    expect(w.find('.policy-badge').text()).toBe('Standard')
  })

  it('cycles the policy on badge click (standard → full_auto → ask)', async () => {
    const store = useAgentSettingsStore()
    const w = mount(ChatHeader, {
      props: { tokenUsage: { prompt: 0, completion: 0 } },
      global: { plugins: [i18n] },
    })
    expect(store.policy).toBe('standard')

    await w.find('.policy-badge').trigger('click')
    expect(store.policy).toBe('full_auto')
    expect(w.find('.policy-badge').text()).toBe('Auto')

    await w.find('.policy-badge').trigger('click')
    expect(store.policy).toBe('ask')
    expect(w.find('.policy-badge').text()).toBe('Ask')
  })
})
