// @vitest-environment node
/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Tests for useAgent runLoop (Wave 2 Task 2.3) — migrated to @ag-ui/client seam.
 *
 * Each scenario injects a fake AgentLike via `agentFactory` (makeFakeAgent)
 * instead of the old `streamRunFn`. Every behavioural assertion is preserved.
 *
 * Covers:
 *   1. no tool_calls → loop exits after one round
 *   2. 1 tool_call (auto policy) → dispatch + result + re-run + exit
 *   3. confirm-required tool → confirm card pushed; user approves → dispatch
 *   4. confirm-required tool → user cancels → user_cancelled tool result, no dispatch
 *   5. cancel mid-stream → silent cancel → transient cleared, only user message
 *   6. 3 invalid_field strikes → break + synth skipped for remaining
 *   7. cancelRun during confirm wait → resolveAllPendingConfirms(false) + loop breaks
 *   8. clearHistory resets messages + threadId + tokens
 *   9. round-2 wire payload preserves assistant.toolCalls
 *   10. RUN_ERROR produces exactly 1 assistant message
 *   11. cancelRun during confirm → outerStop → no round 2
 */

import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAgent, _resetAgent } from '@/composables/useAgent'
import { useAgentStore } from '@/stores/agent'
import { useAgentSettingsStore } from '@/stores/agentSettings'
import { makeFakeAgent } from '@/composables/__tests__/_fakeAgent'

// Minimal localStorage stub for node environment (agentSettings.ts calls it on init)
const localStorageStore: Record<string, string> = {}
const localStorageStub = {
  getItem: (key: string) => localStorageStore[key] ?? null,
  setItem: (key: string, value: string) => { localStorageStore[key] = value },
  removeItem: (key: string) => { delete localStorageStore[key] },
  clear: () => { for (const k in localStorageStore) delete localStorageStore[k] },
}
Object.defineProperty(globalThis, 'localStorage', {
  value: localStorageStub,
  writable: true,
  configurable: true,
})

// Minimal navigator stub — required by @/i18n's resolveLocale() (called at
// module init via useAgent → i18n.global.t for error formatting).
if (typeof (globalThis as any).navigator === 'undefined') {
  Object.defineProperty(globalThis, 'navigator', {
    value: { language: 'en-US' },
    writable: true,
    configurable: true,
  })
}

// Minimal window stub — getApiBase() (called by useAgent.runLoop when building
// the agent URL) reads window.electron?.backendPort. In node env there is no
// window; provide an empty one so getApiBase() falls back to the relative '/api'.
if (typeof (globalThis as any).window === 'undefined') {
  Object.defineProperty(globalThis, 'window', {
    value: {},
    writable: true,
    configurable: true,
  })
}

beforeEach(() => {
  localStorageStub.clear()
  setActivePinia(createPinia())
  _resetAgent()   // reset singleton so each test gets a fresh instance
})

// ─── Scenario 1 ───────────────────────────────────────────────────────────────

describe('useAgent.runLoop', () => {
  it('no tool_calls → loop exits after one round', async () => {
    const fake = makeFakeAgent(() => ({ textDeltas: ['hi'] }))
    const { sendUserText, messages } = useAgent({ agentFactory: fake.factory })
    await sendUserText('hello')
    expect(fake.agent.runAgent).toHaveBeenCalledTimes(1)
    expect(messages.value.map(m => m.role)).toEqual(['user', 'assistant'])
  })

  // ─── Scenario 2 ────────────────────────────────────────────────────────────

  it('1 tool_call (auto policy) → dispatch + result + re-run + exit', async () => {
    const fake = makeFakeAgent((round) => round === 0
      ? { toolCalls: [{ id: 'tc1', name: 'navigate_to', args: '{"route":"/video"}' }] }
      : { textDeltas: ['done'] })
    const fakeToolsTOOLS = [{ name: 'navigate_to', description: '', parameters: {} }]
    const fakeTools = {
      TOOLS: fakeToolsTOOLS,
      getTools: () => fakeToolsTOOLS,
      dispatch: vi.fn(async () => ({ ok: true })),
    }
    // Default policy is 'auto'; 'navigate_to' is in autoWhitelist (not in alwaysAsk)
    const { sendUserText, messages } = useAgent({ agentFactory: fake.factory, tools: fakeTools })
    await sendUserText('go to video')
    expect(fake.agent.runAgent).toHaveBeenCalledTimes(2)
    expect(fakeTools.dispatch).toHaveBeenCalledOnce()
    expect(messages.value.map(m => m.role)).toEqual(['user', 'assistant', 'tool', 'assistant'])
  })

  // ─── Scenario 3 ────────────────────────────────────────────────────────────

  it('confirm-required tool → confirm card pushed; user approves → dispatch + result', async () => {
    // Use policy='ask_all' so shouldConfirm always returns true regardless of tool name.
    // This ensures the confirm flow is triggered independently of alwaysAsk state.
    const settings = useAgentSettingsStore()
    settings.setPolicy('ask_all')

    // Round-aware: round 1 returns tool_call, round 2 returns empty (exits loop)
    const fake = makeFakeAgent((round) => round === 0
      ? { toolCalls: [{ id: 'tc1', name: 'navigate_to', args: '{"route":"/video"}' }] }
      : { textDeltas: ['done'] })
    const fakeToolsTOOLS = [{ name: 'navigate_to', description: '', parameters: {} }]
    const fakeTools = {
      TOOLS: fakeToolsTOOLS,
      getTools: () => fakeToolsTOOLS,
      dispatch: vi.fn(async () => ({ ok: true })),
    }

    const store = useAgentStore()
    const { sendUserText, messages } = useAgent({ agentFactory: fake.factory, tools: fakeTools })

    // Drive approval: start run + concurrently poll for pending confirms and approve
    let approveCount = 0
    const approver = async () => {
      for (let i = 0; i < 20; i++) {
        await new Promise(r => setTimeout(r, 1))
        if (store.pendingConfirms.size > 0) {
          store.resolveAllPendingConfirms(true)
          approveCount++
          break
        }
      }
    }

    await Promise.all([sendUserText('click it'), approver()])

    expect(approveCount).toBeGreaterThan(0)
    // confirm card + tool result + second assistant message (round 2 returns no tool_calls)
    const roles = messages.value.map(m => m.role)
    expect(roles).toContain('tool_confirm')
    expect(roles).toContain('tool')
    expect(fakeTools.dispatch).toHaveBeenCalledOnce()
    // Second stream call happens after tool result
    expect(fake.agent.runAgent).toHaveBeenCalledTimes(2)
  })

  // ─── Scenario 4 ────────────────────────────────────────────────────────────

  it('confirm-required tool → user cancels → user_cancelled tool result + no dispatch', async () => {
    // Use policy='ask_all' so shouldConfirm always returns true.
    const settings = useAgentSettingsStore()
    settings.setPolicy('ask_all')

    // Round-aware: round 1 returns tool_call requiring confirm, round 2 returns empty (exits loop)
    const fake = makeFakeAgent((round) => round === 0
      ? { toolCalls: [{ id: 'tc1', name: 'navigate_to', args: '{}' }] }
      : { textDeltas: ['done'] })
    const fakeToolsTOOLS = [{ name: 'navigate_to', description: '', parameters: {} }]
    const fakeTools = {
      TOOLS: fakeToolsTOOLS,
      getTools: () => fakeToolsTOOLS,
      dispatch: vi.fn(async () => ({ ok: true })),
    }

    const store = useAgentStore()
    const { sendUserText, messages } = useAgent({ agentFactory: fake.factory, tools: fakeTools })

    // Drive rejection: poll for pending confirms and reject them
    const rejecter = async () => {
      for (let i = 0; i < 20; i++) {
        await new Promise(r => setTimeout(r, 1))
        if (store.pendingConfirms.size > 0) {
          store.resolveAllPendingConfirms(false)
          break
        }
      }
    }

    await Promise.all([sendUserText('click it'), rejecter()])

    expect(fakeTools.dispatch).not.toHaveBeenCalled()
    const toolMessages = messages.value.filter(m => m.role === 'tool')
    // First tool message should be user_cancelled
    expect(toolMessages.length).toBeGreaterThanOrEqual(1)
    const firstToolContent = JSON.parse((toolMessages[0] as any).content)
    expect(firstToolContent.user_cancelled).toBe(true)
  })

  // ─── Scenario 5 ────────────────────────────────────────────────────────────

  it('cancel mid-stream → silent cancel → transient cleared, only user message remains', async () => {
    const store = useAgentStore()

    // Stream emits partial text, then blocks until abortRun() → code:'abort'
    const fake = makeFakeAgent(() => ({ textDeltas: ['partial...'], blockUntilAbort: true }))

    const { sendUserText, cancelRun, messages } = useAgent({ agentFactory: fake.factory })

    // Start the run, let it begin + emit partial, then cancel
    const p = sendUserText('long question')
    await new Promise(r => setTimeout(r, 5))   // let runAgent start + emit partial
    cancelRun()                                 // → abortRun() unblocks fake → code:'abort'
    await p

    // Transient was discarded — no assistant message should appear
    expect(messages.value.map(m => m.role)).toEqual(['user'])
    // Store transient should be cleared
    expect(store.transient).toBeNull()
  })

  // ─── Scenario 6 ────────────────────────────────────────────────────────────

  it('3 invalid_field strikes → break + synth skipped for remaining tool call', async () => {
    const fake = makeFakeAgent(() => ({
      toolCalls: [
        { id: 'tc1', name: 'set_field', args: '{}' },
        { id: 'tc2', name: 'set_field', args: '{}' },
        { id: 'tc3', name: 'set_field', args: '{}' },
        { id: 'tc4', name: 'set_field', args: '{}' },
      ],
    }))
    const fakeToolsTOOLS: { name: string; description: string; parameters: object }[] = []
    const fakeTools = {
      TOOLS: fakeToolsTOOLS,
      getTools: () => fakeToolsTOOLS,
      dispatch: vi.fn(async () => ({ error: 'agent.error.invalid_field' })),
    }
    const { sendUserText, messages } = useAgent({ agentFactory: fake.factory, tools: fakeTools })
    await sendUserText('break it')

    // 3 strikes hit on tc3 → outerStop; tc4 gets synthetic skipped result
    expect(fakeTools.dispatch).toHaveBeenCalledTimes(3)
    const toolMessages = messages.value.filter(m => m.role === 'tool')
    expect(toolMessages).toHaveLength(4)  // 3 real + 1 synth skipped
    const lastContent = JSON.parse((toolMessages[3] as any).content)
    expect(lastContent.skipped).toBe('too_many_strikes')
  })

  // ─── Scenario 7 ────────────────────────────────────────────────────────────

  it('cancelRun during confirm wait → resolveAllPendingConfirms(false) + loop breaks', async () => {
    // Use policy='ask_all' so shouldConfirm always returns true.
    // cancelRun() calls abortRun() AND resolves pending confirms with false +
    // sets outerStop, so the loop stops without a round 2.
    const settings = useAgentSettingsStore()
    settings.setPolicy('ask_all')

    const fake = makeFakeAgent(() => ({
      toolCalls: [{ id: 'tc1', name: 'navigate_to', args: '{}' }],
    }))
    const fakeToolsTOOLS: { name: string; description: string; parameters: object }[] = []
    const fakeTools = {
      TOOLS: fakeToolsTOOLS,
      getTools: () => fakeToolsTOOLS,
      dispatch: vi.fn(async () => ({ ok: true })),
    }

    const store = useAgentStore()
    const { sendUserText, cancelRun, messages } = useAgent({
      agentFactory: fake.factory,
      tools: fakeTools,
    })

    // Drive cancelRun: poll for pending confirms and call cancelRun when one appears
    // cancelRun() calls abortRun() + resolveAllPendingConfirms(false) + outerStop
    const canceller = async () => {
      for (let i = 0; i < 20; i++) {
        await new Promise(r => setTimeout(r, 1))
        if (store.pendingConfirms.size > 0) {
          cancelRun()  // aborts + rejects all pending confirms + outerStop
          break
        }
      }
    }

    await Promise.all([sendUserText('do the action'), canceller()])

    // dispatch was never called because confirmation was rejected via cancelRun
    expect(fakeTools.dispatch).not.toHaveBeenCalled()
    // user_cancelled tool result should be present (from the rejected confirm)
    const toolMessages = messages.value.filter(m => m.role === 'tool')
    expect(toolMessages.length).toBeGreaterThanOrEqual(1)
    const content = JSON.parse((toolMessages[0] as any).content)
    expect(content.user_cancelled).toBe(true)
  })

  // ─── Scenario 8 ────────────────────────────────────────────────────────────

  it('clearHistory resets messages + threadId + tokens', async () => {
    const store = useAgentStore()
    const fake = makeFakeAgent(() => ({ textDeltas: ['hello'] }))

    const { sendUserText, clearHistory, messages, threadId } = useAgent({ agentFactory: fake.factory })

    // Populate some state
    await sendUserText('hello')
    expect(messages.value).toHaveLength(2)

    // Manually add some token usage
    store.addUsage({ promptTokens: 100, completionTokens: 50 })
    expect(store.threadTokens.completion).toBe(50)

    const oldThreadId = threadId.value
    clearHistory()

    expect(messages.value).toHaveLength(0)
    expect(threadId.value).not.toBe(oldThreadId)
    expect(store.threadTokens.prompt).toBe(0)
    expect(store.threadTokens.completion).toBe(0)
  })

  // ─── Transient buffer ────────────────────────────────────────────────────────

  it('transient buffer is committed to messages on clean stream return', async () => {
    const store = useAgentStore()
    let capturedTransient: any = null

    // Fire two text deltas, then capture the transient state mid-stream by
    // wrapping runAgent to read store.transient right after the deltas fired.
    const fake = makeFakeAgent(() => ({ textDeltas: ['hello', ' world'] }))
    const orig = fake.agent.runAgent.getMockImplementation()!
    fake.agent.runAgent.mockImplementation(async (p: any, s: any) => {
      // Wrap the subscriber so we can snapshot transient after deltas are applied.
      const wrapped = {
        ...s,
        onTextMessageContentEvent: (arg: any) => {
          s.onTextMessageContentEvent?.(arg)
          capturedTransient = store.transient ? { ...store.transient } : null
        },
      }
      return orig(p, wrapped)
    })

    const { sendUserText, messages } = useAgent({ agentFactory: fake.factory })
    await sendUserText('hi')

    // Mid-stream: transient should have been set
    expect(capturedTransient).not.toBeNull()
    // After clean return: transient should be cleared
    expect(store.transient).toBeNull()
    // Assistant message committed to messages
    expect(messages.value.find(m => m.role === 'assistant')).toBeDefined()
  })

  // ─── Scenario 9: toolCalls preserved in round-2 wire payload ────────────────

  it('round-2 wire payload preserves assistant.toolCalls (not dropped)', async () => {
    const fake = makeFakeAgent((round) => round === 0
      ? { toolCalls: [{ id: 'tc1', name: 'navigate_to', args: '{"route":"/video"}' }] }
      : { textDeltas: ['done'] })
    const fakeToolsTOOLS = [{ name: 'navigate_to', description: '', parameters: {} }]
    const fakeTools = {
      TOOLS: fakeToolsTOOLS,
      getTools: () => fakeToolsTOOLS,
      dispatch: vi.fn(async () => ({ ok: true })),
    }

    const { sendUserText } = useAgent({ agentFactory: fake.factory, tools: fakeTools })
    await sendUserText('go to video')

    // Round 2 must have been called
    expect(fake.agent.runAgent).toHaveBeenCalledTimes(2)
    const capturedRound2Messages = fake.calls[1].messagesIn
    expect(capturedRound2Messages).not.toBeNull()

    // Find the assistant entry in the round-2 wire payload
    const wireAssistant = capturedRound2Messages.find((m: any) => m.role === 'assistant')
    expect(wireAssistant).toBeDefined()
    // toolCalls must NOT be dropped
    expect(Array.isArray(wireAssistant.toolCalls)).toBe(true)
    expect(wireAssistant.toolCalls).toHaveLength(1)
    expect(wireAssistant.toolCalls[0].id).toBe('tc1')
  })

  // ─── Scenario 10: RUN_ERROR produces exactly 1 assistant message ─────────────

  it('RUN_ERROR does not duplicate assistant message', async () => {
    const fake = makeFakeAgent(() => ({ error: { code: 'agent.error.no_model', message: 'no model configured' } }))

    const { sendUserText, messages } = useAgent({ agentFactory: fake.factory })
    await sendUserText('hello')

    const assistantMessages = messages.value.filter(m => m.role === 'assistant')
    // Must be exactly 1 — the formatted error one, NOT an extra empty follow-up
    expect(assistantMessages).toHaveLength(1)
    const msg = assistantMessages[0] as any
    // useAgent now formats RUN_ERROR via i18n: either translated text or raw
    // code when no translation, followed by the backend message in parens.
    // Both `agent.error.no_model` (raw code if i18n absent) and the en/zh-TW
    // translations are acceptable; the backend message must always be there.
    expect(msg.content).toMatch(/no model configured/)
    expect(msg.content).toMatch(/agent\.error\.no_model|No agent model configured|尚未設定/)
  })

  // ─── Scenario 11: cancelRun during confirm → outerStop → no round 2 ──────────

  it('cancelRun during confirm wait sets outerStop → loop exits, no round 2 runAgent', async () => {
    const settings = useAgentSettingsStore()
    settings.setPolicy('ask_all')

    const fake = makeFakeAgent(() => ({
      toolCalls: [{ id: 'tc1', name: 'navigate_to', args: '{}' }],
    }))
    const fakeToolsTOOLS: { name: string; description: string; parameters: object }[] = []
    const fakeTools = {
      TOOLS: fakeToolsTOOLS,
      getTools: () => fakeToolsTOOLS,
      dispatch: vi.fn(async () => ({ ok: true })),
    }

    const store = useAgentStore()
    const { sendUserText, cancelRun, messages } = useAgent({
      agentFactory: fake.factory,
      tools: fakeTools,
    })

    // Poll for pending confirm card, then call cancelRun()
    const canceller = async () => {
      for (let i = 0; i < 30; i++) {
        await new Promise(r => setTimeout(r, 1))
        if (store.pendingConfirms.size > 0) {
          cancelRun()
          break
        }
      }
    }

    await Promise.all([sendUserText('do the action'), canceller()])

    // runAgent was called exactly ONCE — no round 2
    expect(fake.agent.runAgent).toHaveBeenCalledTimes(1)
    // dispatch was never called (confirm was rejected via cancelRun)
    expect(fakeTools.dispatch).not.toHaveBeenCalled()
    // user_cancelled tool result is present
    const toolMessages = messages.value.filter(m => m.role === 'tool')
    expect(toolMessages.length).toBeGreaterThanOrEqual(1)
    const content = JSON.parse((toolMessages[0] as any).content)
    expect(content.user_cancelled).toBe(true)
  })

  // ─── Non-abort error ─────────────────────────────────────────────────────────

  it('unexpected reject (no RUN_ERROR) → internal error assistant message + loop breaks', async () => {
    const fake = makeFakeAgent(() => ({ newMessages: [] }))
    // override runAgent to reject WITHOUT firing onRunErrorEvent (connection-layer failure)
    fake.agent.runAgent.mockImplementationOnce(async () => { throw new Error('network failure') })

    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { sendUserText, messages } = useAgent({ agentFactory: fake.factory })
    await sendUserText('query')

    expect(messages.value.map(m => m.role)).toEqual(['user', 'assistant'])
    const lastMsg = messages.value[messages.value.length - 1] as any
    expect(lastMsg.content).toContain('agent.error.internal')
    expect(lastMsg.content).toContain('network failure')
    consoleErrorSpy.mockRestore()
  })
})
