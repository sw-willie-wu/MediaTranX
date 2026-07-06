// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en'
import ToolCallCard from '@/components/agent/ToolCallCard.vue'
import ChatMessages from '@/components/agent/ChatMessages.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function mountCard(name: string) {
  return mount(ToolCallCard, {
    props: { toolCall: { id: 't1', function: { name, arguments: '{}' } }, status: 'done' },
    global: { plugins: [i18n] },
  })
}
function mountMessages(messages: any[]) {
  return mount(ChatMessages, {
    props: { messages, transient: null, isRunning: false, runError: null },
    global: { plugins: [i18n] },
  })
}

describe('tool-chip tool-name i18n', () => {
  it('ToolCallCard shows the localized label for a known tool, not the raw name', () => {
    const w = mountCard('navigate_to')
    expect(w.find('.tool-name').text()).toBe('Navigate')        // en agent.tool.navigate_to
    expect(w.find('.tool-name').text()).not.toBe('navigate_to')
  })
  it('ToolCallCard falls back to the raw name for an unknown tool', () => {
    const w = mountCard('some_future_tool')
    expect(w.find('.tool-name').text()).toBe('some_future_tool')
  })
  it('ChatMessages tool-result row shows the localized tool label', () => {
    const messages = [
      { role: 'assistant', content: '', toolCalls: [{ id: 'c1', function: { name: 'navigate_to', arguments: '{}' } }] },
      { role: 'tool', toolCallId: 'c1', content: '{"ok":true}' },
    ]
    const w = mountMessages(messages)
    expect(w.find('.tool-result-name').text()).toBe('Navigate')
  })
})
