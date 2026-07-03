// @vitest-environment jsdom
/* eslint-disable @typescript-eslint/no-explicit-any */
import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { HttpAgent } from '@ag-ui/client'
import { useAgent, _resetAgent } from '@/composables/useAgent'
import { useAgentStore } from '@/stores/agent'
import { useToast } from '@/composables/useToast'
import i18n from '@/i18n'

// Isolate session persistence: commitMessage() now POSTs to /agent/sessions via
// apiFetch. Without this stub those POSTs would hit the global `fetch` mock these
// tests install for the HttpAgent /agent/run calls and desync its single-use SSE
// Response stream (giving phantom-empty toolCalls). getApiBase is still exported
// so the HttpAgent run URL builds normally (HttpAgent uses global fetch, not apiFetch).
vi.mock('@/composables/useApi', () => ({
  getApiBase: () => '/api',
  apiFetch: vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) })),
}))

// ─── Minimal localStorage stub for jsdom environment ─────────────────────────
const lsStore: Record<string, string> = {}
Object.defineProperty(globalThis, 'localStorage', {
  value: {
    getItem: (k: string) => lsStore[k] ?? null,
    setItem: (k: string, v: string) => { lsStore[k] = v },
    removeItem: (k: string) => { delete lsStore[k] },
    clear: () => { for (const k in lsStore) delete lsStore[k] },
  },
  writable: true,
  configurable: true,
})

// ─── SSE wire helpers ─────────────────────────────────────────────────────────
function sseStream(events: Record<string, unknown>[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder()
  const frames = events.map(e => `data: ${JSON.stringify(e)}\n\n`).join('')
  return new ReadableStream({
    start(c) {
      const b = enc.encode(frames)
      const mid = Math.floor(b.length / 2)
      c.enqueue(b.slice(0, mid))
      c.enqueue(b.slice(mid))
      c.close()
    },
  })
}

function respOf(events: Record<string, unknown>[]) {
  return new Response(sseStream(events), {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

function mockFetch(events: Record<string, unknown>[]) {
  return vi.fn().mockResolvedValue(
    new Response(sseStream(events), { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
  )
}

// Round-2 terminator wire: no tool call → runLoop exits after round 2
const TERMINATE = [
  { type: 'RUN_STARTED', threadId: 't', runId: 'r' },
  { type: 'TEXT_MESSAGE_CHUNK', messageId: 'm9', delta: 'done' },
  { type: 'RUN_FINISHED', threadId: 't', runId: 'r' },
]

// ─── Test setup ───────────────────────────────────────────────────────────────
const origFetch = globalThis.fetch
const realAgentFactory = (cfg: any) => new HttpAgent(cfg) as any

beforeEach(() => {
  i18n.global.locale.value = 'en'
  for (const k in lsStore) delete lsStore[k]
  setActivePinia(createPinia())
  _resetAgent()
})
afterEach(() => {
  globalThis.fetch = origFetch
})
afterEach(() => {
  useToast().toasts.splice(0)
})

// ─── Tests ────────────────────────────────────────────────────────────────────
describe('useAgent × real HttpAgent (mock fetch)', () => {

  it('① text + single tool call assembled', async () => {
    // ⚠️ MANDATORY: has tool call → runLoop fires round 2.
    // mockResolvedValueOnce = round 1 (with tool call), mockResolvedValue = round 2 (TERMINATE)
    const round1 = [
      { type: 'RUN_STARTED', threadId: 't1', runId: 'r1' },
      { type: 'TEXT_MESSAGE_CHUNK', messageId: 'm1', role: 'assistant', delta: 'Sure, ' },
      { type: 'TEXT_MESSAGE_CHUNK', messageId: 'm1', delta: 'done.' },
      { type: 'TOOL_CALL_CHUNK', toolCallId: 'tc1', toolCallName: 'set_field', parentMessageId: 'm1', delta: '{"field":"grayscale","value":50}' },
      { type: 'RUN_FINISHED', threadId: 't1', runId: 'r1', usage: { promptTokens: 10, completionTokens: 4 } },
    ]
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(respOf(round1))
      .mockResolvedValue(respOf(TERMINATE)) as any

    const fakeTools = {
      TOOLS: [],
      getTools: () => [{ name: 'set_field', description: '', parameters: {} }],
      dispatch: vi.fn(async () => ({ ok: true })),
    }
    const { sendUserText, messages } = useAgent({ agentFactory: realAgentFactory, tools: fakeTools as any })
    await sendUserText('make it grayscale')

    // Assert on the FIRST assistant message (from round 1)
    const asst = messages.value.find(m => m.role === 'assistant') as any
    expect(asst).toBeDefined()
    expect(asst.content).toBe('Sure, done.')
    expect(asst.toolCalls[0].function.name).toBe('set_field')
    expect(JSON.parse(asst.toolCalls[0].function.arguments)).toEqual({ field: 'grayscale', value: 50 })
  }, 10000)

  it('② phantom empty-name tool call filtered (Bug #9)', async () => {
    // ⚠️ MANDATORY: has a real tool call → runLoop fires round 2.
    const round1 = [
      { type: 'RUN_STARTED', threadId: 't2', runId: 'r2' },
      // phantom: empty name (qwen3 quirk) — sanitizer must filter this out
      { type: 'TOOL_CALL_CHUNK', toolCallId: 'tc_phantom', toolCallName: '', parentMessageId: 'm2', delta: '' },
      // real call
      { type: 'TOOL_CALL_CHUNK', toolCallId: 'tc_real', toolCallName: 'navigate_to', parentMessageId: 'm2', delta: '{"route":"image"}' },
      { type: 'RUN_FINISHED', threadId: 't2', runId: 'r2' },
    ]
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(respOf(round1))
      .mockResolvedValue(respOf(TERMINATE)) as any

    const fakeTools = {
      TOOLS: [],
      getTools: () => [{ name: 'navigate_to', description: '', parameters: {} }],
      dispatch: vi.fn(async () => ({ ok: true })),
    }
    const { sendUserText, messages } = useAgent({ agentFactory: realAgentFactory, tools: fakeTools as any })
    await sendUserText('go')

    // First assistant message should have only 1 tool call (phantom filtered)
    const asst = messages.value.find(m => m.role === 'assistant') as any
    expect(asst).toBeDefined()
    expect(asst.toolCalls).toHaveLength(1)
    expect(asst.toolCalls[0].function.name).toBe('navigate_to')
  }, 10000)

  it('③ truncated args → "{}"', async () => {
    // ⚠️ MANDATORY: has a tool call → runLoop fires round 2.
    const round1 = [
      { type: 'RUN_STARTED', threadId: 't3', runId: 'r3' },
      // Truncated args: model stopped after "{"
      { type: 'TOOL_CALL_CHUNK', toolCallId: 'tc3', toolCallName: 'set_field', parentMessageId: 'm3', delta: '{' },
      { type: 'RUN_FINISHED', threadId: 't3', runId: 'r3' },
    ]
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(respOf(round1))
      .mockResolvedValue(respOf(TERMINATE)) as any

    const fakeTools = {
      TOOLS: [],
      getTools: () => [{ name: 'set_field', description: '', parameters: {} }],
      dispatch: vi.fn(async () => ({ ok: true })),
    }
    const { sendUserText, messages } = useAgent({ agentFactory: realAgentFactory, tools: fakeTools as any })
    await sendUserText('break')

    const asst = messages.value.find(m => m.role === 'assistant') as any
    expect(asst).toBeDefined()
    // normalizeToolCallArgs("{") → "{}"
    expect(asst.toolCalls[0].function.arguments).toBe('{}')
  }, 10000)

  it('④ usage captured from RUN_FINISHED passthrough', async () => {
    // Single-round (no tool call) — plain mockFetch is fine
    globalThis.fetch = mockFetch([
      { type: 'RUN_STARTED', threadId: 't4', runId: 'r4' },
      { type: 'TEXT_MESSAGE_CHUNK', messageId: 'm4', delta: 'ok' },
      { type: 'RUN_FINISHED', threadId: 't4', runId: 'r4', usage: { promptTokens: 12, completionTokens: 3 } },
    ]) as any

    const store = useAgentStore()
    const { sendUserText } = useAgent({ agentFactory: realAgentFactory })
    await sendUserText('hi')

    expect(store.threadTokens.prompt).toBe(12)
    expect(store.threadTokens.completion).toBe(3)
  }, 10000)

  it('⑤ error path (lone terminal RUN_ERROR) → i18n error, no crash', async () => {
    // Single-round (no tool call) — plain mockFetch is fine
    globalThis.fetch = mockFetch([
      { type: 'RUN_STARTED', threadId: 't5', runId: 'r5' },
      { type: 'RUN_ERROR', message: 'no model configured', code: 'agent.error.no_model' },
    ]) as any

    const { toasts } = useToast()
    toasts.splice(0)   // clear any prior toasts before the run

    const { sendUserText, messages } = useAgent({ agentFactory: realAgentFactory })
    await sendUserText('hi')

    expect(messages.value.filter(m => m.role === 'assistant')).toHaveLength(0)
    expect(toasts).toHaveLength(1)
    expect(toasts[0].message).toBe('No assistant model configured')
    expect(useAgentStore().runError).toBe('No assistant model configured')
  }, 10000)

  it('⑤b defensive: RUN_ERROR + trailing RUN_FINISHED → still recovers, no crash', async () => {
    // Non-conformant backend: RUN_ERROR followed by a trailing RUN_FINISHED.
    // Verified real-SDK behavior for THIS wire shape: verifyEvents throws an
    // AGUIError on the trailing RUN_FINISHED *before* RUN_ERROR is dispatched to
    // the subscriber, so onRunErrorEvent does NOT fire (runError stays null) and
    // runAgent rejects → useAgent takes path 4c (caught && !result) → a single
    // `[agent.error.internal] Cannot send event type 'RUN_FINISHED'...` message.
    // The point of this defensive test: a non-conformant wire still yields exactly
    // ONE assistant error message and does NOT crash. (Task 5's backend conformance
    // fix removes this wire shape entirely; the conformant lone-RUN_ERROR case ⑤
    // is the real production path and recovers the i18n code via 4b.)
    globalThis.fetch = mockFetch([
      { type: 'RUN_STARTED', threadId: 't5b', runId: 'r5b' },
      { type: 'RUN_ERROR', message: 'boom', code: 'agent.error.internal' },
      { type: 'RUN_FINISHED', threadId: 't5b', runId: 'r5b' },  // non-conformant trailing event
    ]) as any

    const { sendUserText, messages } = useAgent({ agentFactory: realAgentFactory })
    await sendUserText('hi')

    const asst = messages.value.filter(m => m.role === 'assistant')
    expect(asst).toHaveLength(1)
    expect((asst[0] as any).content).toMatch(/boom|agent\.error\.internal/)
  }, 10000)

  it('⑥ abort → silent cancel, no error message, does not hang', async () => {
    // fetch that never closes until abort signal fires
    globalThis.fetch = vi.fn().mockImplementation((_url: string, init?: RequestInit) =>
      new Promise((resolve, reject) => {
        const signal = init?.signal
        const stream = new ReadableStream<Uint8Array>({
          start(c) {
            c.enqueue(new TextEncoder().encode('data: {"type":"RUN_STARTED","threadId":"t6","runId":"r6"}\n\n'))
            // When abort fires, error the stream so the SDK's reader rejects
            signal?.addEventListener('abort', () => {
              try { c.error(new DOMException('Aborted', 'AbortError')) } catch { /* noop */ }
            })
          },
        })
        if (signal?.aborted) { reject(new DOMException('Aborted', 'AbortError')); return }
        // Also reject the fetch promise itself on abort (belt-and-suspenders)
        signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
        resolve(new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }))
      }),
    ) as any

    const store = useAgentStore()
    const { sendUserText, cancelRun, messages } = useAgent({ agentFactory: realAgentFactory })
    const p = sendUserText('long question that never ends')
    // Let runAgent start and begin consuming the stream
    await new Promise(r => setTimeout(r, 20))
    cancelRun()   // → agent.abortRun() → SDK emits onRunErrorEvent({code:'abort'}) → cancelled=true
    await p

    expect(messages.value.map(m => m.role)).toEqual(['user'])  // silent: no assistant error message
    expect(store.isRunning).toBe(false)
    expect(store.transient).toBeNull()
  }, 10000)
})
