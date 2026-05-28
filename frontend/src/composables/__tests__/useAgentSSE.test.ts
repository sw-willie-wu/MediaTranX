/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Tests for AgUiSSEParser and streamRun()
 *
 * Wire-format assumptions (per Wave 1 SPIKE-A e2e verification):
 *   - Frames: `data: {JSON}\n\n`  — no `event:` line
 *   - Payload discriminated by `payload.type` (camelCase)
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { AgUiSSEParser, streamRun } from '../useAgentSSE'
import type { StreamRunOpts } from '../useAgentSSE'

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Encode an ag_ui SSE frame from a plain object. */
function frame(payload: object): string {
  return `data: ${JSON.stringify(payload)}\n\n`
}

/**
 * Build a mock fetch that returns a ReadableStream whose chunks are the
 * provided sseChunks strings.
 */
function mockFetchStream(sseChunks: string[], status = 200): typeof fetch {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    body: new ReadableStream({
      start(controller) {
        for (const chunk of sseChunks) {
          controller.enqueue(new TextEncoder().encode(chunk))
        }
        controller.close()
      },
    }),
  })
}

/** Minimal StreamRunOpts for streamRun() tests. */
function baseOpts(overrides: Partial<StreamRunOpts> = {}): StreamRunOpts {
  return {
    threadId: 'thread-1',
    runId: 'run-1',
    messages: [],
    tools: [],
    state: {},
    ...overrides,
  }
}

// ─── AgUiSSEParser ─────────────────────────────────────────────────────────────

describe('AgUiSSEParser', () => {
  // ── TEXT_MESSAGE_CHUNK ───────────────────────────────────────────────────────

  it('parses single TEXT_MESSAGE_CHUNK from one feed() call', () => {
    const chunks: Array<{ messageId: string; delta: string }> = []
    const parser = new AgUiSSEParser({ onTextChunk: (e) => chunks.push(e) })
    parser.feed(frame({ type: 'TEXT_MESSAGE_CHUNK', messageId: 'msg-1', delta: 'Hello' }))
    expect(chunks).toHaveLength(1)
    expect(chunks[0]).toEqual({ messageId: 'msg-1', delta: 'Hello' })
  })

  it('assembles text from multiple TEXT_MESSAGE_CHUNK frames', () => {
    const parser = new AgUiSSEParser({})
    parser.feed(frame({ type: 'TEXT_MESSAGE_CHUNK', messageId: 'msg-1', delta: 'Hello' }))
    parser.feed(frame({ type: 'TEXT_MESSAGE_CHUNK', messageId: 'msg-1', delta: ', world' }))
    const msg = parser.assembledAssistantMessage()
    expect(msg.content).toBe('Hello, world')
    expect(msg.id).toBe('msg-1')
    expect(msg.role).toBe('assistant')
  })

  it('handles frame split across multiple feed() calls (partial frames)', () => {
    const chunks: Array<{ messageId: string; delta: string }> = []
    const parser = new AgUiSSEParser({ onTextChunk: (e) => chunks.push(e) })

    const full = frame({ type: 'TEXT_MESSAGE_CHUNK', messageId: 'msg-2', delta: 'split' })
    // Feed in three uneven parts
    const mid = Math.floor(full.length / 2)
    parser.feed(full.slice(0, 5))
    expect(chunks).toHaveLength(0) // not yet a complete frame
    parser.feed(full.slice(5, mid))
    expect(chunks).toHaveLength(0)
    parser.feed(full.slice(mid))
    expect(chunks).toHaveLength(1)
    expect(chunks[0].delta).toBe('split')
  })

  // ── RUN_STARTED / RUN_FINISHED ───────────────────────────────────────────────

  it('dispatches RUN_STARTED, TEXT_MESSAGE_CHUNK*2, RUN_FINISHED in order', () => {
    const events: string[] = []
    const parser = new AgUiSSEParser({
      onRunStarted: () => events.push('started'),
      onTextChunk: () => events.push('text'),
      onRunFinished: () => events.push('finished'),
    })
    parser.feed(frame({ type: 'RUN_STARTED', runId: 'r1', threadId: 't1' }))
    parser.feed(frame({ type: 'TEXT_MESSAGE_CHUNK', messageId: 'msg-1', delta: 'A' }))
    parser.feed(frame({ type: 'TEXT_MESSAGE_CHUNK', messageId: 'msg-1', delta: 'B' }))
    parser.feed(frame({ type: 'RUN_FINISHED', runId: 'r1', threadId: 't1' }))
    expect(events).toEqual(['started', 'text', 'text', 'finished'])
  })

  it('RUN_STARTED passes correct runId and threadId', () => {
    let received: { runId: string; threadId: string } | null = null
    const parser = new AgUiSSEParser({
      onRunStarted: (e) => { received = e },
    })
    parser.feed(frame({ type: 'RUN_STARTED', runId: 'run-42', threadId: 'thread-99' }))
    expect(received).toEqual({ runId: 'run-42', threadId: 'thread-99' })
  })

  it('RUN_FINISHED passes usage with camelCase fields', () => {
    let usage: any = null
    const parser = new AgUiSSEParser({
      onRunFinished: (e) => { usage = e.usage },
    })
    parser.feed(frame({
      type: 'RUN_FINISHED',
      runId: 'r1',
      threadId: 't1',
      usage: { promptTokens: 120, completionTokens: 45 },
    }))
    expect(usage).toEqual({ promptTokens: 120, completionTokens: 45 })
  })

  // ── TOOL_CALL_CHUNK ──────────────────────────────────────────────────────────

  it('accumulates TOOL_CALL_CHUNK args by toolCallId', () => {
    const toolChunks: any[] = []
    const parser = new AgUiSSEParser({
      onToolCallChunk: (e) => toolChunks.push({ ...e }),
    })
    parser.feed(frame({
      type: 'TOOL_CALL_CHUNK',
      toolCallId: 'tc-1',
      toolCallName: 'navigate_to',
      parentMessageId: 'msg-1',
      delta: '{"route"',
    }))
    parser.feed(frame({
      type: 'TOOL_CALL_CHUNK',
      toolCallId: 'tc-1',
      parentMessageId: 'msg-1',
      delta: ':"/video"}',
    }))
    // Two callbacks fired
    expect(toolChunks).toHaveLength(2)
    expect(toolChunks[0].toolCallName).toBe('navigate_to')
    expect(toolChunks[1].toolCallName).toBe('navigate_to') // name preserved from first chunk

    // assembledAssistantMessage reflects accumulated args
    const msg = parser.assembledAssistantMessage()
    expect(msg.toolCalls).toHaveLength(1)
    expect(msg.toolCalls[0].id).toBe('tc-1')
    expect(msg.toolCalls[0].function.name).toBe('navigate_to')
    expect(msg.toolCalls[0].function.arguments).toBe('{"route":"/video"}')
  })

  it('accumulates two independent tool calls separately', () => {
    const parser = new AgUiSSEParser({})
    parser.feed(frame({
      type: 'TOOL_CALL_CHUNK',
      toolCallId: 'tc-A',
      toolCallName: 'tool_a',
      parentMessageId: 'msg-1',
      delta: 'argA',
    }))
    parser.feed(frame({
      type: 'TOOL_CALL_CHUNK',
      toolCallId: 'tc-B',
      toolCallName: 'tool_b',
      parentMessageId: 'msg-1',
      delta: 'argB',
    }))
    const msg = parser.assembledAssistantMessage()
    expect(msg.toolCalls).toHaveLength(2)
    const names = msg.toolCalls.map((tc) => tc.function.name).sort()
    expect(names).toEqual(['tool_a', 'tool_b'])
  })

  // ── RUN_ERROR ────────────────────────────────────────────────────────────────

  it('dispatches RUN_ERROR with code and message', () => {
    let err: { code: string; message: string } | null = null
    const parser = new AgUiSSEParser({ onError: (e) => { err = e } })
    parser.feed(frame({ type: 'RUN_ERROR', code: 'MODEL_UNAVAILABLE', message: 'Model is offline' }))
    expect(err).toEqual({ code: 'MODEL_UNAVAILABLE', message: 'Model is offline' })
  })

  // ── Resilience ───────────────────────────────────────────────────────────────

  it('skips malformed JSON gracefully and processes subsequent valid frames', () => {
    const chunks: any[] = []
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const parser = new AgUiSSEParser({ onTextChunk: (e) => chunks.push(e) })

    // Send a malformed frame followed by a valid one
    parser.feed('data: {not valid json}\n\n')
    parser.feed(frame({ type: 'TEXT_MESSAGE_CHUNK', messageId: 'msg-1', delta: 'ok' }))

    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('[useAgentSSE] malformed SSE payload:'),
      expect.any(String),
    )
    expect(chunks).toHaveLength(1)
    expect(chunks[0].delta).toBe('ok')
    warnSpy.mockRestore()
  })

  it('skips unknown event type with console.warn', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const parser = new AgUiSSEParser({})
    parser.feed(frame({ type: 'CUSTOM_VENDOR_EVENT', data: 123 }))
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('[useAgentSSE] unknown event type:'),
      'CUSTOM_VENDOR_EVENT',
    )
    warnSpy.mockRestore()
  })

  it('handles CR-LF line endings in the SSE stream', () => {
    const chunks: any[] = []
    const parser = new AgUiSSEParser({ onTextChunk: (e) => chunks.push(e) })
    // Simulate CRLF from a Windows SSE server
    const crlf = `data: ${JSON.stringify({ type: 'TEXT_MESSAGE_CHUNK', messageId: 'msg-1', delta: 'crlf' })}\r\n\r\n`
    parser.feed(crlf)
    expect(chunks).toHaveLength(1)
    expect(chunks[0].delta).toBe('crlf')
  })

  it('handles multi-line data: (valid split JSON object across lines) in a single frame', () => {
    // SSE spec: multiple `data:` lines in one frame are concatenated with \n.
    // A JSON *object* split across two data: lines at a field boundary is valid.
    // Note: splitting mid-string is NOT valid JSON after join; split at property boundaries.
    const part1 = '{"type":"TEXT_MESSAGE_CHUNK",'
    const part2 = '"messageId":"msg-x","delta":"multi"}'
    const multiLineFrame = `data: ${part1}\ndata: ${part2}\n\n`
    const chunks: any[] = []
    const parser = new AgUiSSEParser({ onTextChunk: (e) => chunks.push(e) })
    parser.feed(multiLineFrame)
    expect(chunks).toHaveLength(1)
    expect(chunks[0].delta).toBe('multi')
  })
})

// ─── streamRun ─────────────────────────────────────────────────────────────────

describe('streamRun', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('POSTs correct body shape to /api/agent/run', async () => {
    const mockFetch = mockFetchStream([
      frame({ type: 'RUN_STARTED', runId: 'r1', threadId: 't1' }),
      frame({ type: 'TEXT_MESSAGE_CHUNK', messageId: 'msg-1', delta: 'hi' }),
      frame({ type: 'RUN_FINISHED', runId: 'r1', threadId: 't1' }),
    ])
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetch as any)

    await streamRun(baseOpts({
      threadId: 'thread-abc',
      runId: 'run-xyz',
      messages: [{ id: 'u1', role: 'user', content: 'Hello' }],
      tools: [{ name: 'tool_a', description: 'desc', parameters: {} }],
      state: { key: 'val' },
    }))

    expect(fetch).toHaveBeenCalledOnce()
    const [url, init] = (fetch as any).mock.calls[0]
    expect(url).toContain('/agent/run')
    expect(init.method).toBe('POST')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(init.headers['Accept']).toBe('text/event-stream')

    const body = JSON.parse(init.body)
    expect(body.threadId).toBe('thread-abc')
    expect(body.runId).toBe('run-xyz')
    expect(body.messages).toEqual([{ id: 'u1', role: 'user', content: 'Hello' }])
    expect(body.tools).toEqual([{ name: 'tool_a', description: 'desc', parameters: {} }])
    expect(body.state).toEqual({ key: 'val' })
    // Required fields present
    expect(body.context).toEqual([])
    expect(body.forwardedProps).toEqual({})
  })

  it('returns assembled AssistantMessage from full SSE stream', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetchStream([
      frame({ type: 'RUN_STARTED', runId: 'r1', threadId: 't1' }),
      frame({ type: 'TEXT_MESSAGE_CHUNK', messageId: 'msg-1', delta: 'Hello' }),
      frame({ type: 'TEXT_MESSAGE_CHUNK', messageId: 'msg-1', delta: ', world' }),
      frame({ type: 'RUN_FINISHED', runId: 'r1', threadId: 't1', usage: { promptTokens: 10, completionTokens: 5 } }),
    ]) as any)

    const msg = await streamRun(baseOpts())
    expect(msg.id).toBe('msg-1')
    expect(msg.role).toBe('assistant')
    expect(msg.content).toBe('Hello, world')
    expect(msg.toolCalls).toHaveLength(0)
  })

  it('returns AssistantMessage with tool calls', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetchStream([
      frame({ type: 'RUN_STARTED', runId: 'r1', threadId: 't1' }),
      frame({ type: 'TOOL_CALL_CHUNK', toolCallId: 'tc-1', toolCallName: 'my_tool', parentMessageId: 'msg-2', delta: '{"x":1}' }),
      frame({ type: 'RUN_FINISHED', runId: 'r1', threadId: 't1' }),
    ]) as any)

    const msg = await streamRun(baseOpts())
    expect(msg.toolCalls).toHaveLength(1)
    expect(msg.toolCalls[0]).toEqual({
      id: 'tc-1',
      type: 'function',
      function: { name: 'my_tool', arguments: '{"x":1}' },
    })
  })

  it('fires onRunStarted, onTextChunk, onRunFinished callbacks', async () => {
    const events: string[] = []
    const textDeltas: string[] = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetchStream([
      frame({ type: 'RUN_STARTED', runId: 'r1', threadId: 't1' }),
      frame({ type: 'TEXT_MESSAGE_CHUNK', messageId: 'msg-1', delta: 'part1' }),
      frame({ type: 'TEXT_MESSAGE_CHUNK', messageId: 'msg-1', delta: 'part2' }),
      frame({ type: 'RUN_FINISHED', runId: 'r1', threadId: 't1' }),
    ]) as any)

    await streamRun(baseOpts({
      onRunStarted: () => events.push('started'),
      onTextChunk: (e) => textDeltas.push(e.delta),
      onRunFinished: () => events.push('finished'),
    }))

    expect(events).toEqual(['started', 'finished'])
    expect(textDeltas).toEqual(['part1', 'part2'])
  })

  it('throws agent.error.http_500 on server error', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetchStream([], 500) as any)
    await expect(streamRun(baseOpts())).rejects.toThrow('agent.error.http_500')
  })

  it('handles stream split across chunks (partial SSE frames)', async () => {
    // Simulate network sending partial frame, then completion
    const full = frame({ type: 'TEXT_MESSAGE_CHUNK', messageId: 'msg-1', delta: 'partial' })
    const mid = Math.floor(full.length / 2)
    vi.spyOn(globalThis, 'fetch').mockImplementation(mockFetchStream([
      full.slice(0, mid),
      full.slice(mid),
    ]) as any)

    const msg = await streamRun(baseOpts())
    expect(msg.content).toBe('partial')
  })

  it('propagates AbortError when signal is aborted', async () => {
    const controller = new AbortController()
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => {
      controller.abort()
      return Promise.reject(new DOMException('The user aborted a request.', 'AbortError'))
    })

    await expect(
      streamRun(baseOpts({ signal: controller.signal }))
    ).rejects.toThrow(/aborted/i)
  })
})
