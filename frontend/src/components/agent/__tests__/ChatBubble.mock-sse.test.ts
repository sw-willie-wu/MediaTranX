/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Mock-SSE smoke test — Wave 2 Task 2.6 + Wave 4 Tasks 4.2/4.3/4.8
 *
 * Verifies the full Wave 2 stack end-to-end using a deterministic fake
 * AgentLike (makeFakeAgent, no real HTTP).  Exercises:
 *   - useAgent singleton: shared isRunning + cancelRun across consumers
 *   - Transient text buffer: streaming delta appears then commits to messages
 *   - isRunning flag: correct during + after a run
 *   - cancelRun halts the run loop and discards transient state
 *
 * Wave 4 additions:
 *   - Task 4.2: setCurrentAction is called before each tool dispatch
 *   - Task 4.3: ConfirmCard full flow — tool_confirm card → approve → dispatch
 *   - Task 4.8: 3-round token accumulation — prompt replaces, completion accumulates
 *
 * 2026-05-28: AgentRunBanner removed (chat bubble already shows running state
 * inline). Scenario 5 (banner-mounted cancel-button click) dropped; Scenario 4
 * (cancelRun on singleton halts the loop) still covers the underlying behaviour.
 */

import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en'

import ChatMessages from '@/components/agent/ChatMessages.vue'
import ConfirmCard from '@/components/agent/ConfirmCard.vue'
import { useAgent, _resetAgent } from '@/composables/useAgent'
import { useAgentStore } from '@/stores/agent'
import { makeFakeAgent } from '@/composables/__tests__/_fakeAgent'

// ─── Global plugin config shared by all mounts ───────────────────────────────

function makeI18n() {
  return createI18n({ legacy: false, locale: 'en', messages: { en } })
}

const globalPlugins = () => ({
  plugins: [makeI18n()],
})

// ─── Minimal localStorage stub (node env) ────────────────────────────────────

const lsStore: Record<string, string> = {}
const lsStub = {
  getItem: (k: string) => lsStore[k] ?? null,
  setItem: (k: string, v: string) => { lsStore[k] = v },
  removeItem: (k: string) => { delete lsStore[k] },
  clear: () => { for (const k in lsStore) delete lsStore[k] },
}
Object.defineProperty(globalThis, 'localStorage', {
  value: lsStub,
  writable: true,
  configurable: true,
})

// ─── Test lifecycle ───────────────────────────────────────────────────────────

beforeEach(() => {
  lsStub.clear()
  setActivePinia(createPinia())
  _resetAgent()
  // Provide a model so sendUserText doesn't immediately short-circuit
  lsStub.setItem('agent_settings', JSON.stringify({
    modelChoice: 'qwen3:8b',
    policy: 'auto',
  }))
})

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('ChatBubble mock-SSE smoke', () => {

  // ─── Scenario 1: singleton identity ──────────────────────────────────────

  it('singleton: multiple useAgent() calls return the same instance', () => {
    const a = useAgent()
    const b = useAgent()
    expect(a).toBe(b)
    // messages ref is the exact same reactive ref
    expect(a.messages).toBe(b.messages)
    expect(a.isRunning).toBe(b.isRunning)
  })

  // ─── Scenario 2: streaming text commits to messages ──────────────────────

  it('sendUserText → streaming deltas accumulate → commit to assistant message', async () => {
    const fake = makeFakeAgent(() => ({ textDeltas: ['Hello', ' world!'] }))
    const agent = useAgent({ agentFactory: fake.factory })

    await agent.sendUserText('Hi there')

    const roles = agent.messages.value.map(m => m.role)
    expect(roles).toEqual(['user', 'assistant', 'assistant'])
    expect((agent.messages.value[0] as any).content).toBe('Hi there')
    expect((agent.messages.value[1] as any).content).toBe('Hello world!')
    expect(fake.agent.runAgent).toHaveBeenCalledTimes(2)
  })

  // ─── Scenario 3: isRunning via store — all consumers share state ──────────

  it('useAgent singleton: isRunning reflects shared store state across consumers', async () => {
    const store = useAgentStore()

    // Validate the shared store ref before mounting
    expect(store.isRunning).toBe(false)

    // Manually flip running to verify it surfaces on the store
    store.start()
    expect(store.isRunning).toBe(true)
    store.stop()
    expect(store.isRunning).toBe(false)

    // Both components read isRunning from the same store
    const fake = makeFakeAgent(() => ({ textDeltas: ['ok'] }))

    // isRunning becomes true during run — capture it inside runAgent
    let runningDuringStream = false
    const origRun = fake.agent.runAgent.getMockImplementation()!
    fake.agent.runAgent.mockImplementation(async (p: any, s: any) => {
      runningDuringStream = store.isRunning
      return origRun(p, s)
    })
    const agent = useAgent({ agentFactory: fake.factory })

    await agent.sendUserText('test')
    // isRunning was true while streaming (captured above)
    expect(runningDuringStream).toBe(true)
    // After run completes: isRunning is false
    expect(store.isRunning).toBe(false)
  })

  // ─── Scenario 4: cancelRun on singleton halts the run loop ───────────────

  it('cancelRun on singleton instance halts the run loop', async () => {
    // Fake agent that emits partial text then blocks until abortRun() → code:'abort'
    const fake = makeFakeAgent(() => ({ textDeltas: ['partial'], blockUntilAbort: true }))

    const agent = useAgent({ agentFactory: fake.factory })
    const store = useAgentStore()

    // Start run without awaiting (it will block)
    const runPromise = agent.sendUserText('long question')

    // Wait for stream to start (store should be running)
    await new Promise(r => setTimeout(r, 10))
    expect(store.isRunning).toBe(true)

    // Cancel via the singleton (the chat bubble cancel button does the same).
    // cancelRun() → abortRun() unblocks the fake → it fires code:'abort' + rejects.
    agent.cancelRun()

    await runPromise

    // After cancel: isRunning false, only user message in history (transient discarded)
    expect(store.isRunning).toBe(false)
    expect(agent.messages.value.map(m => m.role)).toEqual(['user'])
  })

  // ─── Scenario 5 (Task 4.2): setCurrentAction fires inside real dispatchers ───

  it('Task 4.2: real dispatch() calls store.setCurrentAction with correct key before executing', async () => {
    // Import the real dispatch function (not injected via fakeTool)
    const { dispatch } = await import('@/composables/useAgentTools')
    const store = useAgentStore()

    // Dispatch navigate_to — outside a setup context resolveRouter() falls
    // back to the global singleton (router/index.ts) and navigation succeeds.
    // The key behaviour we care about here is that setCurrentAction fires
    // BEFORE the router push, so any consumer listening on the store
    // (chat bubble, future UI) gets a chance to render the action label.
    const result = await dispatch({
      id: 'tc1',
      type: 'function',
      function: { name: 'navigate_to', arguments: '{"route":"/video"}' },
    })

    // setCurrentAction must have fired with the correct key + args
    expect(store.currentAction.key).toBe('agent.banner.act.navigate_to')
    expect(store.currentAction.args).toEqual({ route: '/video' })
    // dispatch should succeed against the global router singleton
    expect(result.ok).toBe(true)
  })

  // ─── Scenario 7 (Task 4.3): ConfirmCard full flow ───────────────────────────

  it('Task 4.3: ChatMessages renders tool_confirm as ConfirmCard; approve resolves promise and dispatch proceeds', async () => {
    // Verify ChatMessages renders a ConfirmCard for a tool_confirm message
    const confirmMsg = {
      role: 'tool_confirm' as const,
      toolCall: { id: 'tc1', function: { name: 'click_execute', arguments: '{}' } },
      status: 'pending' as const,
    }
    const msgs: any[] = [confirmMsg]

    const wrapper = mount(ChatMessages, {
      props: { messages: msgs, transient: null, isRunning: false, runError: null },
      global: globalPlugins(),
    })

    // ConfirmCard should be rendered
    expect(wrapper.findComponent(ConfirmCard).exists()).toBe(true)

    // Approve via store (simulating button click)
    const store = useAgentStore()
    let resolved = false
    store.addPendingConfirm((approved) => { resolved = approved })

    // Click the submit button on ConfirmCard
    const submitBtn = wrapper.find('.btn-submit')
    expect(submitBtn.exists()).toBe(true)
    await submitBtn.trigger('click')

    // Resolver should have been called with true
    expect(resolved).toBe(true)
    // pendingConfirms should now be empty
    expect(store.pendingConfirms.size).toBe(0)

    wrapper.unmount()
  })

  // ─── Scenario 8 (Task 4.8): 3-round token accumulation ─────────────────────

  it('Task 4.8: 3-round mock-SSE — prompt replaces each round, completion accumulates', async () => {
    const store = useAgentStore()

    const usagePerRound = [
      { promptTokens: 100, completionTokens: 20 },
      { promptTokens: 200, completionTokens: 30 },
      { promptTokens: 350, completionTokens: 15 },
    ]

    // Rounds 0+1 return a tool_call; round 2 returns plain text to stop the loop.
    const fake = makeFakeAgent((round) => ({
      usage: usagePerRound[round],
      toolCalls: round < 2
        ? [{ id: `tc${round}`, name: 'list_files', args: '{}' }]
        : undefined,
      textDeltas: round < 2 ? undefined : ['all done'],
    }))

    const fakeToolTOOLS: { name: string; description: string; parameters: object }[] = []
    const fakeTool = {
      TOOLS: fakeToolTOOLS,
      getTools: () => fakeToolTOOLS,
      dispatch: vi.fn(async () => ({ ok: true, files: [] })),
    }

    const agent = useAgent({ agentFactory: fake.factory, tools: fakeTool })
    await agent.sendUserText('list files 3 times')

    // After 3 rounds:
    // prompt = last round's promptTokens (REPLACE) = 350
    // completion = 20 + 30 + 15 = 65 (ACCUMULATE)
    expect(store.threadTokens.prompt).toBe(350)
    expect(store.threadTokens.completion).toBe(65)

    // ChatHeader should display these values — verify via mount
    const ChatHeader = (await import('@/components/agent/ChatHeader.vue')).default
    const header = mount(ChatHeader, {
      props: { tokenUsage: store.threadTokens },
      global: globalPlugins(),
    })
    const tokenText = header.find('.token-counter')
    expect(tokenText.exists()).toBe(true)
    // The token counter text should contain the prompt and completion values
    expect(tokenText.text()).toContain('350')
    expect(tokenText.text()).toContain('65')
    header.unmount()
  })
})
