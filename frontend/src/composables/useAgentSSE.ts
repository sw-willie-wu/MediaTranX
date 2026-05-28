/**
 * useAgentSSE — SSE parser + streamRun() for ag-ui agent backend.
 *
 * Wire format (per Wave 1 SPIKE-A e2e verification):
 *   - Each frame:  data: {JSON}\n\n   (no `event:` line)
 *   - Payload discriminated by `payload.type` (camelCase field names)
 *   - Event types: RUN_STARTED, TEXT_MESSAGE_CHUNK, TOOL_CALL_CHUNK,
 *                  RUN_FINISHED, RUN_ERROR
 *
 * Tool shape: flat ag_ui `{name, description, parameters}` (NOT OpenAI-nested).
 */

import { getApiBase } from '@/composables/useApi'

// ─── Public types ──────────────────────────────────────────────────────────────

export interface AgUiTool {
  name: string
  description: string
  parameters: object
}

export interface AgUiMessage {
  id: string
  role: string
  content: string
  toolCalls?: { id: string; function: { name: string; arguments: string } }[]
  toolCallId?: string
}

export interface StreamRunOpts {
  threadId: string
  runId: string
  messages: AgUiMessage[]
  tools: AgUiTool[]
  state: Record<string, unknown>
  signal?: AbortSignal
  // Stream-time callbacks
  onTextChunk?: (e: { messageId: string; delta: string }) => void
  onToolCallChunk?: (e: { toolCallId: string; toolCallName: string; parentMessageId: string; delta: string }) => void
  onRunStarted?: (e: { runId: string; threadId: string }) => void
  onRunFinished?: (e: { runId: string; threadId: string; usage?: { promptTokens: number; completionTokens: number } }) => void
  onError?: (e: { code: string; message: string }) => void
}

export interface AssistantMessage {
  id: string              // = messageId from first TEXT_MESSAGE_CHUNK
  role: 'assistant'
  content: string         // concatenated text deltas
  toolCalls: Array<{
    id: string
    type: 'function'
    function: { name: string; arguments: string }
  }>
}

// ─── Internal callback bag ─────────────────────────────────────────────────────

type StreamRunCallbacks = Pick<
  StreamRunOpts,
  'onTextChunk' | 'onToolCallChunk' | 'onRunStarted' | 'onRunFinished' | 'onError'
>

// ─── AgUiSSEParser ─────────────────────────────────────────────────────────────

export class AgUiSSEParser {
  private buf = ''
  /** messageId → concatenated text */
  private textAccum = new Map<string, string>()
  /** toolCallId → accumulated tool call */
  private toolCallsAccum = new Map<string, { name: string; args: string; firstMessageId: string }>()
  private lastMessageId = ''

  constructor(private callbacks: StreamRunCallbacks) {}

  /**
   * Feed a raw text chunk (potentially partial SSE frames) into the parser.
   * Fires callbacks synchronously for each complete frame found.
   */
  feed(chunk: string): void {
    // Normalise CRLF → LF before buffering so the frame delimiter search
    // (\n\n) works regardless of whether the server uses LF or CRLF.
    this.buf += chunk.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
    let nl: number
    // Frames are delimited by \n\n; parse only complete frames.
    while ((nl = this.buf.indexOf('\n\n')) !== -1) {
      const frame = this.buf.slice(0, nl)
      this.buf = this.buf.slice(nl + 2)
      this.parseFrame(frame)
    }
  }

  private parseFrame(frame: string): void {
    // Collect all `data:` lines from this frame, concat, then JSON-parse.
    // ag_ui emits one data line per frame; multi-line support is defensive.
    const dataLines: string[] = []
    for (const line of frame.split('\n')) {
      if (line.startsWith('data: ')) {
        dataLines.push(line.slice(6))
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5))
      }
      // Other SSE fields (event:, id:, retry:) are intentionally ignored.
    }
    if (dataLines.length === 0) return

    const payloadStr = dataLines.join('\n')
    let payload: unknown
    try {
      payload = JSON.parse(payloadStr)
    } catch {
      // Log + skip malformed; don't fail the entire stream.
      console.warn('[useAgentSSE] malformed SSE payload:', payloadStr)
      return
    }

    const type: string = payload.type
    switch (type) {
      case 'RUN_STARTED':
        this.callbacks.onRunStarted?.({ runId: payload.runId, threadId: payload.threadId })
        break

      case 'TEXT_MESSAGE_CHUNK': {
        const messageId: string = payload.messageId
        const delta: string = payload.delta ?? ''
        this.lastMessageId = messageId
        this.textAccum.set(messageId, (this.textAccum.get(messageId) ?? '') + delta)
        this.callbacks.onTextChunk?.({ messageId, delta })
        break
      }

      case 'TOOL_CALL_CHUNK': {
        const toolCallId: string = payload.toolCallId
        const existing = this.toolCallsAccum.get(toolCallId)
        const toolCallName: string =
          payload.toolCallName ?? existing?.name ?? ''
        const parentMessageId: string =
          payload.parentMessageId ?? this.lastMessageId
        const delta: string = payload.delta ?? ''

        if (existing) {
          existing.args += delta
          // Update name if a later chunk provides it (ag_ui sends name on first chunk only)
          if (payload.toolCallName) existing.name = toolCallName
        } else {
          this.toolCallsAccum.set(toolCallId, {
            name: toolCallName,
            args: delta,
            firstMessageId: parentMessageId,
          })
        }
        this.callbacks.onToolCallChunk?.({ toolCallId, toolCallName, parentMessageId, delta })
        break
      }

      case 'RUN_FINISHED':
        this.callbacks.onRunFinished?.({
          runId: payload.runId,
          threadId: payload.threadId,
          usage: payload.usage,
        })
        break

      case 'RUN_ERROR':
        this.callbacks.onError?.({ code: payload.code, message: payload.message })
        break

      default:
        console.warn('[useAgentSSE] unknown event type:', type)
    }
  }

  /**
   * Return the assembled AssistantMessage after the stream ends.
   * Includes ALL accumulated tool calls (single-round: all belong to this message).
   */
  assembledAssistantMessage(): AssistantMessage {
    const normalizeToolCallArgs = (raw: string): string => {
      const trimmed = (raw ?? '').trim()
      if (!trimmed) return '{}'
      try {
        JSON.parse(trimmed)
        return trimmed
      } catch {
        return '{}'
      }
    }
    const id = this.lastMessageId || crypto.randomUUID()
    const content = this.textAccum.get(id) ?? ''
    // Drop tool calls with a missing / empty name — qwen3 etc. occasionally
    // emit phantom `{name: ""}` entries alongside a real call (Bug #9). These
    // would dispatch to nothing (unknown_tool) and pollute the round-2 wire,
    // where llama-server's tool-call parser then rejects them with a 500.
    const toolCalls = Array.from(this.toolCallsAccum.entries())
      .filter(([_, v]) => v.name && v.name.trim())
      .map(([toolCallId, v]) => ({
        id: toolCallId,
        type: 'function' as const,
        // Normalize the streamed `arguments` to a valid JSON-encoded object.
        // Three failure modes observed live with qwen3-8b:
        //   1. Empty: model emits no args at all → ""
        //   2. Truncated: model stops mid-stream after "{" (no closing brace)
        //   3. Garbage: model emits trailing text or non-JSON noise
        // Any non-parseable value defaults to "{}" so neither the frontend
        // dispatcher's JSON.parse nor llama-server's tool-call parser
        // (next-round payload) explodes.
        function: {
          name: v.name,
          arguments: normalizeToolCallArgs(v.args),
        },
      }))
    return { id, role: 'assistant', content, toolCalls }
  }
}

// ─── streamRun ─────────────────────────────────────────────────────────────────

/**
 * POST to /api/agent/run, consume the SSE response, and return the assembled
 * AssistantMessage when the stream ends.
 *
 * Throws `Error('agent.error.http_<status>')` on non-2xx responses.
 * Re-throws `AbortError` if `opts.signal` is aborted.
 */
export async function streamRun(opts: StreamRunOpts): Promise<AssistantMessage> {
  const parser = new AgUiSSEParser({
    onTextChunk: opts.onTextChunk,
    onToolCallChunk: opts.onToolCallChunk,
    onRunStarted: opts.onRunStarted,
    onRunFinished: opts.onRunFinished,
    onError: opts.onError,
  })

  const resp = await fetch(`${getApiBase()}/agent/run`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({
      threadId: opts.threadId,
      runId: opts.runId,
      messages: opts.messages,
      tools: opts.tools,
      state: opts.state,
      context: [],
      forwardedProps: {},
    }),
    signal: opts.signal,
  })

  if (!resp.ok || !resp.body) {
    throw new Error(`agent.error.http_${resp.status}`)
  }

  const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader()
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      if (value) parser.feed(value)
    }
  } finally {
    try {
      reader.releaseLock()
    } catch {
      // releaseLock can throw if the stream is already cancelled; ignore.
    }
  }

  return parser.assembledAssistantMessage()
}
