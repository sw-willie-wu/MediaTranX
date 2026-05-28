/**
 * SPIKE — Does @ag-ui/client HttpAgent consume OUR backend's exact SSE wire?
 *
 * Goal: prove/disprove migration feasibility from hand-rolled useAgentSSE.ts
 * to the official @ag-ui/client HttpAgent, WITHOUT a live backend.
 *
 * Method: mock global fetch to return a ReadableStream of the exact bytes our
 * backend emits (RUN_STARTED / TEXT_MESSAGE_CHUNK / TOOL_CALL_CHUNK / RUN_FINISHED,
 * camelCase JSON via EventEncoder, `data: {JSON}\n\n` framing, no `event:` line),
 * then run HttpAgent.runAgent() and inspect the assembled RunAgentResult.
 *
 * Edge cases tested (the hard-won bug fixes baked into useAgentSSE.ts):
 *   - Bug #9: phantom tool_call chunk with empty name alongside a real call
 *   - Truncated tool-call args (model stops mid-stream after "{")
 *   - Empty args ("")
 *
 * RUN: npx vitest run src/composables/__tests__/_spike_ag_ui_client.test.ts
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { HttpAgent } from '@ag-ui/client'

// ─── Helper: build a fake SSE ReadableStream from a list of event objects ────
function sseStreamFromEvents(events: Record<string, unknown>[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  const frames = events.map(e => `data: ${JSON.stringify(e)}\n\n`).join('')
  return new ReadableStream({
    start(controller) {
      // Emit in a few chunks to mimic real network fragmentation
      const bytes = encoder.encode(frames)
      const mid = Math.floor(bytes.length / 2)
      controller.enqueue(bytes.slice(0, mid))
      controller.enqueue(bytes.slice(mid))
      controller.close()
    },
  })
}

function mockFetchWith(events: Record<string, unknown>[]) {
  return vi.fn().mockResolvedValue(
    new Response(sseStreamFromEvents(events), {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    }),
  )
}

describe('SPIKE: @ag-ui/client HttpAgent vs our backend wire', () => {
  const origFetch = globalThis.fetch

  beforeEach(() => { vi.restoreAllMocks() })
  afterEach(() => { globalThis.fetch = origFetch })

  it('SPIKE-1: consumes a clean text + single tool_call round', async () => {
    // Mirror what AgentService.run emits for "navigate then set_field"
    const events = [
      { type: 'RUN_STARTED', threadId: 't1', runId: 'r1' },
      { type: 'TEXT_MESSAGE_CHUNK', messageId: 'm1', role: 'assistant', delta: 'Sure, ' },
      { type: 'TEXT_MESSAGE_CHUNK', messageId: 'm1', delta: 'doing it.' },
      { type: 'TOOL_CALL_CHUNK', toolCallId: 'tc1', toolCallName: 'set_field', parentMessageId: 'm1', delta: '{"field":"grayscale",' },
      { type: 'TOOL_CALL_CHUNK', toolCallId: 'tc1', delta: '"value":50}' },
      { type: 'RUN_FINISHED', threadId: 't1', runId: 'r1' },
    ]
    globalThis.fetch = mockFetchWith(events) as unknown as typeof fetch

    const agent = new HttpAgent({ url: 'http://localhost/api/agent/run', threadId: 't1' })
    const result = await agent.runAgent({ runId: 'r1', tools: [], context: [] })

    console.log('[SPIKE-1] newMessages:', JSON.stringify(result.newMessages, null, 2))
    expect(result.newMessages.length).toBeGreaterThan(0)
    const asst = result.newMessages.find(m => m.role === 'assistant')
    expect(asst).toBeTruthy()
    // Assembled text
    expect((asst as { content?: string }).content).toBe('Sure, doing it.')
    // Assembled tool call
    const toolCalls = (asst as { toolCalls?: { function: { name: string; arguments: string } }[] }).toolCalls ?? []
    expect(toolCalls.length).toBe(1)
    expect(toolCalls[0].function.name).toBe('set_field')
    expect(JSON.parse(toolCalls[0].function.arguments)).toEqual({ field: 'grayscale', value: 50 })
  })

  it('SPIKE-2: Bug #9 — phantom empty-name tool_call alongside a real one', async () => {
    const events = [
      { type: 'RUN_STARTED', threadId: 't2', runId: 'r2' },
      // phantom: empty name (qwen3 quirk)
      { type: 'TOOL_CALL_CHUNK', toolCallId: 'tc_phantom', toolCallName: '', parentMessageId: 'm2', delta: '' },
      // real call
      { type: 'TOOL_CALL_CHUNK', toolCallId: 'tc_real', toolCallName: 'navigate_to', parentMessageId: 'm2', delta: '{"route":"image"}' },
      { type: 'RUN_FINISHED', threadId: 't2', runId: 'r2' },
    ]
    globalThis.fetch = mockFetchWith(events) as unknown as typeof fetch

    const agent = new HttpAgent({ url: 'http://localhost/api/agent/run', threadId: 't2' })
    let threw: unknown = null
    let result: Awaited<ReturnType<HttpAgent['runAgent']>> | null = null
    try {
      result = await agent.runAgent({ runId: 'r2', tools: [], context: [] })
    } catch (e) {
      threw = e
    }
    console.log('[SPIKE-2] threw:', threw)
    console.log('[SPIKE-2] newMessages:', JSON.stringify(result?.newMessages, null, 2))
    // We don't assert pass/fail here — this is the KEY observation:
    // does verifyEvents/transformChunks choke on the empty-name chunk?
  })

  it('SPIKE-3: truncated tool-call args (model stops after "{")', async () => {
    const events = [
      { type: 'RUN_STARTED', threadId: 't3', runId: 'r3' },
      { type: 'TOOL_CALL_CHUNK', toolCallId: 'tc3', toolCallName: 'set_field', parentMessageId: 'm3', delta: '{' },
      { type: 'RUN_FINISHED', threadId: 't3', runId: 'r3' },
    ]
    globalThis.fetch = mockFetchWith(events) as unknown as typeof fetch

    const agent = new HttpAgent({ url: 'http://localhost/api/agent/run', threadId: 't3' })
    let threw: unknown = null
    let result: Awaited<ReturnType<HttpAgent['runAgent']>> | null = null
    try {
      result = await agent.runAgent({ runId: 'r3', tools: [], context: [] })
    } catch (e) {
      threw = e
    }
    console.log('[SPIKE-3] threw:', threw)
    console.log('[SPIKE-3] newMessages:', JSON.stringify(result?.newMessages, null, 2))
    // KEY observation: does untruncate-json salvage "{" → "{}"?
  })

  it('SPIKE-4: abortRun() cancels mid-stream', async () => {
    // Mock fetch that honors the AbortSignal HttpAgent passes internally,
    // mirroring real fetch() behavior (reject with AbortError on abort).
    globalThis.fetch = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      return new Promise((resolve, reject) => {
        const signal = init?.signal
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            const enc = new TextEncoder()
            controller.enqueue(enc.encode('data: {"type":"RUN_STARTED","threadId":"t4","runId":"r4"}\n\n'))
            // never close — simulate long-running inference
            if (signal) {
              signal.addEventListener('abort', () => {
                try { controller.error(new DOMException('Aborted', 'AbortError')) } catch { /* noop */ }
              })
            }
          },
        })
        if (signal?.aborted) {
          reject(new DOMException('Aborted', 'AbortError'))
          return
        }
        signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
        resolve(new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }))
      })
    }) as unknown as typeof fetch

    const agent = new HttpAgent({ url: 'http://localhost/api/agent/run', threadId: 't4' })
    const runP = agent.runAgent({ runId: 'r4', tools: [], context: [] })
    setTimeout(() => agent.abortRun(), 50)
    let threw: unknown = null
    let result: unknown = null
    try {
      result = await runP
    } catch (e) {
      threw = e
    }
    console.log('[SPIKE-4] abort threw:', threw, '| result:', result)
    // KEY observation: abortRun() terminates the run (either resolves with
    // partial result or rejects). Either way it must NOT hang.
    expect(threw !== null || result !== null).toBe(true)
  }, 10000)
})
