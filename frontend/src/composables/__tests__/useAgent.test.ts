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
 *   2. 1 tool_call (standard policy) → dispatch + result + re-run + exit
 *   3. confirm-required tool → confirm card pushed; user approves → dispatch
 *   4. confirm-required tool → user cancels → user_cancelled tool result, no dispatch
 *   5. cancel mid-stream → silent cancel → transient cleared, only user message
 *   6. 3 invalid_field strikes → break + synth skipped for remaining
 *   7. cancelRun during confirm wait → resolveAllPendingConfirms(false) + loop breaks
 *   8. startNewSession resets messages + threadId + tokens
 *   9. round-2 wire payload preserves assistant.toolCalls
 *   10. RUN_ERROR produces exactly 1 assistant message
 *   11. cancelRun during confirm → outerStop → no round 2
 */

import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useAgent, _resetAgent } from '@/composables/useAgent'
import { useAgentStore } from '@/stores/agent'
import { useAgentSettingsStore } from '@/stores/agentSettings'
import { makeFakeAgent } from '@/composables/__tests__/_fakeAgent'
import { apiFetch } from '@/composables/useApi'
import type { ActivePanelEntry } from '@/composables/useActivePanel'
import type { PanelHandle } from '@/stores/panelRegistry'
import { useToast } from '@/composables/useToast'
import i18n from '@/i18n'

vi.mock('@/composables/useApi', () => ({
  getApiBase: () => '/api',
  apiFetch: vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) })),
}))

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
  i18n.global.locale.value = 'en'
  localStorageStub.clear()
  setActivePinia(createPinia())
  _resetAgent()   // reset singleton so each test gets a fresh instance
  vi.mocked(apiFetch).mockReset()
  vi.mocked(apiFetch).mockResolvedValue({ ok: true, json: () => Promise.resolve({}) } as Response)
})
afterEach(() => {
  useToast().toasts.splice(0)
})

// ─── Scenario 1 ───────────────────────────────────────────────────────────────

describe('useAgent.runLoop', () => {
  it('text-only reply with no action → nudged once, then exits (2 rounds)', async () => {
    const fake = makeFakeAgent(() => ({ textDeltas: ['hi'] }))
    const { sendUserText, messages } = useAgent({ agentFactory: fake.factory })
    await sendUserText('hello')
    expect(fake.agent.runAgent).toHaveBeenCalledTimes(2)   // nudge safety net
    expect(messages.value.map(m => m.role)).toEqual(['user', 'assistant'])
  })

  // ─── Scenario 2 ────────────────────────────────────────────────────────────

  it('1 tool_call (standard policy) → dispatch + result + re-run + exit', async () => {
    const fake = makeFakeAgent((round) => round === 0
      ? { toolCalls: [{ id: 'tc1', name: 'navigate_to', args: '{"route":"/video"}' }] }
      : { textDeltas: ['done'] })
    const fakeToolsTOOLS = [{ name: 'navigate_to', description: '', parameters: {} }]
    const fakeTools = {
      TOOLS: fakeToolsTOOLS,
      getTools: () => fakeToolsTOOLS,
      dispatch: vi.fn(async () => ({ ok: true })),
    }
    // Default policy is 'standard'; 'navigate_to' is non-execute → auto-run (no confirm)
    const { sendUserText, messages } = useAgent({ agentFactory: fake.factory, tools: fakeTools })
    await sendUserText('go to video')
    expect(fake.agent.runAgent).toHaveBeenCalledTimes(3)
    expect(fakeTools.dispatch).toHaveBeenCalledOnce()
    expect(messages.value.map(m => m.role)).toEqual(['user', 'assistant', 'tool', 'assistant'])
  })

  // ─── Scenario 3 ────────────────────────────────────────────────────────────

  it('confirm-required tool → confirm card pushed; user approves → dispatch + result', async () => {
    // Use policy='ask' so shouldConfirm always returns true regardless of tool name.
    // This ensures the confirm flow is triggered independently of alwaysAsk state.
    const settings = useAgentSettingsStore()
    settings.setPolicy('ask')

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
    // Second stream call happens after tool result; third is the nudge round (navigate_to is non-terminal)
    expect(fake.agent.runAgent).toHaveBeenCalledTimes(3)
  })

  // ─── Scenario 4 ────────────────────────────────────────────────────────────

  it('confirm-required tool → user cancels → user_cancelled tool result + no dispatch', async () => {
    // Use policy='ask' so shouldConfirm always returns true.
    const settings = useAgentSettingsStore()
    settings.setPolicy('ask')

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
    // Use policy='ask' so shouldConfirm always returns true.
    // cancelRun() calls abortRun() AND resolves pending confirms with false +
    // sets outerStop, so the loop stops without a round 2.
    const settings = useAgentSettingsStore()
    settings.setPolicy('ask')

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

  it('startNewSession resets messages + threadId + sessionId + tokens', async () => {
    const store = useAgentStore()
    const fake = makeFakeAgent(() => ({ textDeltas: ['hello'] }))

    const { sendUserText, startNewSession, messages, threadId, currentSessionId } =
      useAgent({ agentFactory: fake.factory })

    await sendUserText('hello')
    expect(messages.value).toHaveLength(2)

    store.addUsage({ promptTokens: 100, completionTokens: 50 })
    expect(store.threadTokens.completion).toBe(50)

    const oldThreadId = threadId.value
    const oldSessionId = currentSessionId.value
    startNewSession()

    expect(messages.value).toHaveLength(0)
    expect(threadId.value).not.toBe(oldThreadId)
    expect(currentSessionId.value).not.toBe(oldSessionId)
    expect(threadId.value).toBe(currentSessionId.value)   // 1:1 with thread_id
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

    // Round 2 must have been called (plus a nudge round 3 since navigate_to is non-terminal)
    expect(fake.agent.runAgent).toHaveBeenCalledTimes(3)
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

  // ─── Scenario 10: RUN_ERROR → transient sticky toast, NOT persisted ──────────

  it('RUN_ERROR → sticky error toast, not committed to chat history', async () => {
    const { toasts } = useToast(); toasts.splice(0)
    const fake = makeFakeAgent(() => ({ error: { code: 'agent.error.no_model', message: 'no model configured' } }))

    const { sendUserText, messages } = useAgent({ agentFactory: fake.factory })
    await sendUserText('hello')

    expect(messages.value.map(m => m.role)).toEqual(['user'])
    expect(toasts).toHaveLength(1)
    expect(toasts[0].type).toBe('error')
    expect(toasts[0].message).toBe('No assistant model configured')
    expect(useAgentStore().runError).toBe('No assistant model configured')
  })

  it('RUN_ERROR with an unmapped code → generic friendly fallback (never raw key)', async () => {
    const { toasts } = useToast(); toasts.splice(0)
    const fake = makeFakeAgent(() => ({ error: { code: 'agent.error.some_unmapped', message: 'boom' } }))
    const store = useAgentStore()
    const { sendUserText } = useAgent({ agentFactory: fake.factory })
    await sendUserText('hi')
    expect(toasts[0].message).toBe('The assistant hit an error, please try again later.')
    expect(store.runError).toBe('The assistant hit an error, please try again later.')
    expect(toasts[0].message).not.toContain('agent.error')
  })

  it('sendUserText clears a prior runError label', async () => {
    const store = useAgentStore()
    store.setRunError('previous error')
    const fake = makeFakeAgent(() => ({ textDeltas: ['hi'] }))
    const { sendUserText } = useAgent({ agentFactory: fake.factory })
    await sendUserText('again')
    expect(store.runError).toBeNull()
  })

  // ─── Scenario 11: cancelRun during confirm → outerStop → no round 2 ──────────

  it('cancelRun during confirm wait sets outerStop → loop exits, no round 2 runAgent', async () => {
    const settings = useAgentSettingsStore()
    settings.setPolicy('ask')

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

  // ─── Nudge A: text-only round, not yet acted → inject 1 nudge, re-run ────────

  it('text-only round with no prior action → injects one non-persisted user nudge and re-runs', async () => {
    // Every round is text-only (no tool calls) and no execute/action ever dispatched.
    const fake = makeFakeAgent(() => ({ textDeltas: ['我現在執行壓縮'] }))
    const { sendUserText, messages } = useAgent({ agentFactory: fake.factory })

    await sendUserText('壓縮這張圖並執行')

    // Round 0 (text-only, not acted) → nudge → Round 1 (text-only, nudged) → break.
    expect(fake.agent.runAgent).toHaveBeenCalledTimes(2)
    // The nudge is NOT rendered/persisted: messages.value holds only user + the first assistant text.
    // (nudge round's text-only reply is suppressed — only user + 1 assistant committed)
    expect(messages.value.map(m => m.role)).toEqual(['user', 'assistant'])
    // Round-2 wire payload ends with the injected user nudge, which MUST carry an id.
    const wire2 = fake.calls[1].messagesIn
    const last = wire2[wire2.length - 1]
    expect(last.role).toBe('user')
    expect(typeof last.id).toBe('string')
    expect(last.id.length).toBeGreaterThan(0)
    expect(last.content).toMatch(/尚未執行的操作|直接呼叫對應的工具/)
  })

  // ─── Nudge B: already acted (execute dispatched) → no nudge ──────────────────

  it('text-only round AFTER a click_execute was dispatched → no nudge', async () => {
    const settings = useAgentSettingsStore()
    settings.setPolicy('standard')   // still confirm-gated: click_execute is execute-class
    const fake = makeFakeAgent((round) => round === 0
      ? { toolCalls: [{ id: 'tc1', name: 'click_execute', args: '{}' }] }
      : { textDeltas: ['已送出，稍候'] })
    const fakeToolsTOOLS = [{ name: 'click_execute', description: '', parameters: {} }]
    const fakeTools = {
      TOOLS: fakeToolsTOOLS,
      getTools: () => fakeToolsTOOLS,
      dispatch: vi.fn(async () => ({ ok: true, task_id: 't1' })),
    }
    const store = useAgentStore()
    const { sendUserText } = useAgent({ agentFactory: fake.factory, tools: fakeTools })

    // Approve the confirm card when it appears.
    const approver = async () => {
      for (let i = 0; i < 30; i++) {
        await new Promise(r => setTimeout(r, 1))
        if (store.pendingConfirms.size > 0) { store.resolveAllPendingConfirms(true); break }
      }
    }
    await Promise.all([sendUserText('執行'), approver()])

    // Round 0 execute + Round 1 text-only(acted→no nudge, break) = exactly 2, NOT 3.
    expect(fake.agent.runAgent).toHaveBeenCalledTimes(2)
    // No wire payload contains an injected nudge user message.
    const anyNudge = fake.calls.some(c =>
      c.messagesIn.some((m: any) => m.role === 'user' && /直接呼叫對應的工具/.test(m.content ?? '')))
    expect(anyNudge).toBe(false)
  })

  // ─── Nudge C: user CANCELS the execute confirm → still no nudge (M1) ──────────

  it('user cancels the execute confirm, next text-only round → no nudge (acted set at dequeue)', async () => {
    const settings = useAgentSettingsStore()
    settings.setPolicy('standard')
    const fake = makeFakeAgent((round) => round === 0
      ? { toolCalls: [{ id: 'tc1', name: 'click_execute', args: '{}' }] }
      : { textDeltas: ['好，已取消'] })
    const fakeToolsTOOLS = [{ name: 'click_execute', description: '', parameters: {} }]
    const fakeTools = {
      TOOLS: fakeToolsTOOLS,
      getTools: () => fakeToolsTOOLS,
      dispatch: vi.fn(async () => ({ ok: true })),
    }
    const store = useAgentStore()
    const { sendUserText } = useAgent({ agentFactory: fake.factory, tools: fakeTools })

    // Reject the confirm card when it appears.
    const rejecter = async () => {
      for (let i = 0; i < 30; i++) {
        await new Promise(r => setTimeout(r, 1))
        if (store.pendingConfirms.size > 0) { store.resolveAllPendingConfirms(false); break }
      }
    }
    await Promise.all([sendUserText('執行'), rejecter()])

    // Cancel did NOT dispatch, but actedThisTurn was set at dequeue → round-1 text-only NOT nudged.
    expect(fakeTools.dispatch).not.toHaveBeenCalled()
    expect(fake.agent.runAgent).toHaveBeenCalledTimes(2)   // NOT 3 (no nudge round)
    const anyNudge = fake.calls.some(c =>
      c.messagesIn.some((m: any) => m.role === 'user' && /直接呼叫對應的工具/.test(m.content ?? '')))
    expect(anyNudge).toBe(false)
  })

  // ─── Nudge D: nudge round emits a tool call → kept and dispatched ────────────

  it('nudge round that emits a tool call → kept and dispatched (forgotten-action caught)', async () => {
    const fake = makeFakeAgent((round) => round === 0
      ? { textDeltas: ['好的，我現在切換'] }
      : round === 1
        ? { toolCalls: [{ id: 'tc1', name: 'navigate_to', args: '{"route":"/image"}' }] }
        : { textDeltas: ['已切換'] })
    const fakeToolsTOOLS = [{ name: 'navigate_to', description: '', parameters: {} }]
    const fakeTools = { TOOLS: fakeToolsTOOLS, getTools: () => fakeToolsTOOLS, dispatch: vi.fn(async () => ({ ok: true })) }
    const { sendUserText, messages } = useAgent({ agentFactory: fake.factory, tools: fakeTools })
    await sendUserText('切換到圖片工具')
    expect(fakeTools.dispatch).toHaveBeenCalledOnce()
    const roles = messages.value.map(m => m.role)
    expect(roles).toContain('tool')
    expect(roles.filter(r => r === 'assistant').length).toBeGreaterThanOrEqual(1)
  })

  // ─── Persistence tests ──────────────────────────────────────────────────────

  it('persists every committed message via apiFetch', async () => {
    vi.mocked(apiFetch).mockClear()
    const fake = makeFakeAgent(() => ({ textDeltas: ['hi there'] }))
    const { sendUserText, currentSessionId } = useAgent({ agentFactory: fake.factory })

    await sendUserText('hello')

    // user message + one assistant reply (nudge round suppressed) persisted to the session endpoint
    const calls = vi.mocked(apiFetch).mock.calls.filter(
      (c) => String(c[0]).includes(`/agent/sessions/${currentSessionId.value}/messages`),
    )
    expect(calls.length).toBe(2)
    for (const c of calls) {
      expect(c[1]?.method).toBe('POST')
    }
  })

  it('swallows persist failure (in-memory messages stay authoritative)', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response)
    const fake = makeFakeAgent(() => ({ textDeltas: ['hi'] }))
    const { sendUserText, messages } = useAgent({ agentFactory: fake.factory })

    // must not throw even though the first persist returns !ok
    await expect(sendUserText('hello')).resolves.toBeUndefined()
    expect(messages.value).toHaveLength(2)
  })

  // ─── loadSession / deleteSession ────────────────────────────────────────────

  it('loadSession populates messages + sets sessionId/threadId + recreates agent + resets tokens', async () => {
    const store = useAgentStore()
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        id: 's-load',
        messages: [
          { role: 'user', content: 'hi' },
          { role: 'assistant', content: 'hello back' },
        ],
      }),
    } as Response)

    const fake = makeFakeAgent(() => ({ textDeltas: ['x'] }))
    const { loadSession, messages, threadId, currentSessionId } = useAgent({ agentFactory: fake.factory })
    store.addUsage({ promptTokens: 10, completionTokens: 5 })

    await loadSession('s-load')

    expect(messages.value).toHaveLength(2)
    expect(currentSessionId.value).toBe('s-load')
    expect(threadId.value).toBe('s-load')
    expect(store.threadTokens.prompt).toBe(0)
    expect(store.threadTokens.completion).toBe(0)
  })

  it('loadSession sanitizes dangling tool_calls and orphan tool rows', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        id: 's-bad',
        messages: [
          { role: 'user', content: 'do it' },
          // assistant references c1 (matched) and c2 (no tool row -> dropped)
          { role: 'assistant', content: '', toolCalls: [
            { id: 'c1', function: { name: 'set_field', arguments: '{}' } },
            { id: 'c2', function: { name: 'set_field', arguments: '{}' } },
          ] },
          { role: 'tool', content: '{}', toolCallId: 'c1' },
          // orphan tool row (no assistant call) -> dropped
          { role: 'tool', content: '{}', toolCallId: 'zzz' },
        ],
      }),
    } as Response)

    const fake = makeFakeAgent(() => ({ textDeltas: ['x'] }))
    const { loadSession, messages } = useAgent({ agentFactory: fake.factory })

    await loadSession('s-bad')

    // user, assistant(with only c1), tool(c1) — orphan zzz dropped
    expect(messages.value).toHaveLength(3)
    const asst = messages.value[1] as { role: 'assistant'; toolCalls?: { id: string }[] }
    expect(asst.toolCalls?.map((t) => t.id)).toEqual(['c1'])
    const toolIds = messages.value.filter((m) => m.role === 'tool').map((m) => (m as { toolCallId: string }).toolCallId)
    expect(toolIds).toEqual(['c1'])
  })

  it('loadSession throws on fetch failure (caller shows toast)', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ ok: false, status: 500 } as Response)
    const fake = makeFakeAgent(() => ({ textDeltas: ['x'] }))
    const { loadSession } = useAgent({ agentFactory: fake.factory })
    await expect(loadSession('s1')).rejects.toThrow()
  })

  it('deleteSession of the active session starts a new one', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) } as Response)
    const fake = makeFakeAgent(() => ({ textDeltas: ['x'] }))
    const { deleteSession, currentSessionId } = useAgent({ agentFactory: fake.factory })
    const active = currentSessionId.value

    await deleteSession(active)

    expect(currentSessionId.value).not.toBe(active)
  })

  // ─── Agent state snapshot ────────────────────────────────────────────────────

  it('attaches a cloneable two-tier snapshot to agent.state', async () => {
    const handle = {
      agentSchema: {
        panelId: 'video.transcode',
        fields: [{ name: 'output_format', type: 'enum', options: () => ['mp4', 'mkv'] }],
        actions: [],
        execute: { requiresConfirm: true, label: 'Transcode' },
      },
      getCurrentValues: () => ({ output_format: 'mp4' }),
      setField: () => undefined,
      openField: () => {},
      execute: async () => ({}),
      isMultiSelect: () => false,
      isMounted: { value: true } as any,
    } as unknown as PanelHandle
    const activePanel: ActivePanelEntry = {
      panelId: 'video.transcode', schema: handle.agentSchema, instance: handle, isMounted: true,
    }

    const fake = makeFakeAgent(() => ({ textDeltas: ['ok'] }))
    const { sendUserText } = useAgent({
      agentFactory: fake.factory,
      activePanelRef: () => activePanel,
    })
    await sendUserText('hi')

    const state = (fake.agent as any).state
    expect(state.agent_model_choice).toBeDefined()
    expect(state.snapshot.map.views.length).toBeGreaterThan(0)
    expect(state.snapshot.map.current_position.view).toBe('/video')
    expect(state.snapshot.active_panel.panel_id).toBe('video.transcode')
    expect(state.snapshot.active_panel.fields[0].current_value).toBe('mp4')
    expect(() => structuredClone(state)).not.toThrow()
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

  // ─── In-flight abort (fix/agent-abort-inflight) ──────────────────────────────

  it('cancel during an in-flight dispatch → signal aborted + remaining tool calls balanced', async () => {
    // One round emits TWO tool calls. We hold dispatch #1 open, press stop while
    // it is in flight, then let it finish. The run must: (a) abort the signal the
    // dispatcher received, (b) never dispatch tc2, (c) still leave a tool row for
    // BOTH tc1 and tc2 so the history stays balanced (no dangling tool_call).
    const fake = makeFakeAgent((round) => round === 0
      ? { toolCalls: [
          { id: 'tc1', name: 'navigate_to', args: '{"route":"/video"}' },
          { id: 'tc2', name: 'navigate_to', args: '{"route":"/audio"}' },
        ] }
      : { textDeltas: ['done'] })

    let markStarted!: () => void
    const dispatchStarted = new Promise<void>((r) => { markStarted = r })
    let openGate!: () => void
    const gate = new Promise<void>((r) => { openGate = r })
    let capturedSignal: AbortSignal | undefined

    const fakeToolsTOOLS = [{ name: 'navigate_to', description: '', parameters: {} }]
    const fakeTools = {
      TOOLS: fakeToolsTOOLS,
      getTools: () => fakeToolsTOOLS,
      dispatch: vi.fn(async (_tc: any, ctx?: { signal?: AbortSignal }) => {
        capturedSignal = ctx?.signal
        markStarted()
        await gate
        // Mimic the real dispatcher: refuse to apply the mutation if aborted.
        return ctx?.signal?.aborted ? { error: 'agent.error.aborted' } : { ok: true }
      }),
    }

    const { sendUserText, cancelRun, messages } = useAgent({ agentFactory: fake.factory, tools: fakeTools })
    const run = sendUserText('go')
    await dispatchStarted   // dispatch #1 is now in flight
    cancelRun()             // user presses stop mid-dispatch
    openGate()              // let dispatch #1 resolve
    await run

    expect(capturedSignal?.aborted).toBe(true)          // signal threaded + aborted at the right moment
    expect(fakeTools.dispatch).toHaveBeenCalledOnce()   // tc2 never dispatched (loop broke)
    const toolRows = messages.value.filter(m => m.role === 'tool') as any[]
    expect(toolRows.map(m => m.toolCallId).sort()).toEqual(['tc1', 'tc2'])  // balanced
  })

  it('two tool calls without cancel → both dispatched with a non-aborted signal, both tool rows', async () => {
    const fake = makeFakeAgent((round) => round === 0
      ? { toolCalls: [
          { id: 'tc1', name: 'navigate_to', args: '{"route":"/video"}' },
          { id: 'tc2', name: 'navigate_to', args: '{"route":"/audio"}' },
        ] }
      : { textDeltas: ['done'] })

    const seenAborted: boolean[] = []
    const fakeToolsTOOLS = [{ name: 'navigate_to', description: '', parameters: {} }]
    const fakeTools = {
      TOOLS: fakeToolsTOOLS,
      getTools: () => fakeToolsTOOLS,
      dispatch: vi.fn(async (_tc: any, ctx?: { signal?: AbortSignal }) => {
        seenAborted.push(!!ctx?.signal?.aborted)
        return { ok: true }
      }),
    }

    const { sendUserText, messages } = useAgent({ agentFactory: fake.factory, tools: fakeTools })
    await sendUserText('go')

    expect(fakeTools.dispatch).toHaveBeenCalledTimes(2)
    expect(seenAborted).toEqual([false, false])   // signal is present but never aborted on the happy path
    const toolRows = messages.value.filter(m => m.role === 'tool') as any[]
    expect(toolRows.map(m => m.toolCallId).sort()).toEqual(['tc1', 'tc2'])   // exactly two, no double-synth
  })
})
