/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * @vitest-environment jsdom
 *
 * Task 1.6 — AC-12 production activePanelRef wiring smoke.
 *
 * Verifies that in a real <script setup> context (jsdom + router mock +
 * panelRegistry pre-populated), useAgent() picks up useActivePanel()
 * and tools.getTools sees the active panel's schema (not null).
 */
import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { viewRegistry } from '@/stores/viewRegistry'
import { useAgent, _resetAgent } from '@/composables/useAgent'

function makeMockPanelHandle(panelId: string): PanelHandle {
  return {
    agentSchema: {
      panelId,
      fields: [
        { name: 'mock_field_a', type: 'string' },
        { name: 'mock_field_b', type: 'number', min: 0, max: 10 },
      ],
      actions: [],
      execute: { requiresConfirm: false },
    },
    isMultiSelect: () => false,
    getCurrentValues: () => ({ mock_field_a: '', mock_field_b: 0 }),
    setField: (_f: string, _v: unknown) => _v,
    openField: () => {},
    execute: async () => ({}),
    isMounted: ref(true),
  }
}

describe('useAgent production wiring (AC-12)', () => {
  let router: ReturnType<typeof createRouter>

  beforeEach(() => {
    setActivePinia(createPinia())
    _resetAgent()
    panelRegistry._clearAll()
    viewRegistry._clearAll()  // N2 fix — prevent cross-test leak
    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/image', component: { template: '<div/>' } },
        { path: '/', component: { template: '<div/>' } },
      ],
    })
  })

  it('getTools is called with active panel schema when panel + view registered', async () => {
    // Pre-populate registries to simulate a mounted ImageView + ImageAdjustPanel
    viewRegistry.register('image', {
      currentFunction: ref('adjust'),
      setCurrentFunction: (_id: string) => {},
    })
    panelRegistry.register('image.adjust', makeMockPanelHandle('image.adjust'))
    await router.push('/image')
    await router.isReady()

    // Mock streamRun: capture the tools arg passed by useAgent
    let capturedTools: any = null
    const fakeStreamRun = vi.fn(async (input: any) => {
      capturedTools = input.tools
      return { id: 'm1', role: 'assistant' as const, content: 'ok', toolCalls: [] }
    })

    // Mount a host component that calls useAgent() in setup
    const host = defineComponent({
      setup() {
        const agent = useAgent({ streamRunFn: fakeStreamRun })
        return { agent }
      },
      template: '<div/>',
    })
    const w = mount(host, {
      global: { plugins: [router] },
    })
    await w.vm.agent.sendUserText('hi')

    // Verify captured tools array contains a set_field tool with field enum
    expect(capturedTools).toBeDefined()
    const setFieldTool = capturedTools.find((t: any) => t.name === 'set_field')
    expect(setFieldTool).toBeDefined()
    expect(setFieldTool.parameters.properties.field.enum).toEqual(['mock_field_a', 'mock_field_b'])
  })

  it('getTools fallback to free string when no active panel', async () => {
    // No view/panel registered → useActivePanel returns null → free string fallback
    await router.push('/')
    await router.isReady()

    let capturedTools: any = null
    const fakeStreamRun = vi.fn(async (input: any) => {
      capturedTools = input.tools
      return { id: 'm1', role: 'assistant' as const, content: 'ok', toolCalls: [] }
    })

    const host = defineComponent({
      setup() {
        const agent = useAgent({ streamRunFn: fakeStreamRun })
        return { agent }
      },
      template: '<div/>',
    })
    const w = mount(host, { global: { plugins: [router] } })
    await w.vm.agent.sendUserText('hi')

    const setFieldTool = capturedTools.find((t: any) => t.name === 'set_field')
    expect(setFieldTool.parameters.properties.field).toEqual({ type: 'string' })
    expect(setFieldTool.parameters.properties.field.enum).toBeUndefined()
  })

  it('getActivePanel updates when route changes mid-conversation', async () => {
    // First round: home (no panel) → next round: /image with adjust panel registered
    viewRegistry.register('image', {
      currentFunction: ref('adjust'),
      setCurrentFunction: (_id: string) => {},
    })
    panelRegistry.register('image.adjust', makeMockPanelHandle('image.adjust'))

    let capturedTools_round1: any = null
    let capturedTools_round2: any = null
    let round = 0
    const fakeStreamRun = vi.fn(async (input: any) => {
      round++
      if (round === 1) capturedTools_round1 = input.tools
      if (round === 2) capturedTools_round2 = input.tools
      return { id: `m${round}`, role: 'assistant' as const, content: 'ok', toolCalls: [] }
    })

    const host = defineComponent({
      setup() {
        const agent = useAgent({ streamRunFn: fakeStreamRun })
        return { agent }
      },
      template: '<div/>',
    })
    await router.push('/')
    await router.isReady()
    const w = mount(host, { global: { plugins: [router] } })
    await w.vm.agent.sendUserText('first')

    // Navigate to /image then send another message
    await router.push('/image')
    await router.isReady()
    await w.vm.agent.sendUserText('second')

    const sf1 = capturedTools_round1.find((t: any) => t.name === 'set_field')
    const sf2 = capturedTools_round2.find((t: any) => t.name === 'set_field')
    expect(sf1.parameters.properties.field.enum).toBeUndefined()  // round 1: home, no panel
    expect(sf2.parameters.properties.field.enum).toEqual(['mock_field_a', 'mock_field_b'])  // round 2: image.adjust active
  })
})
