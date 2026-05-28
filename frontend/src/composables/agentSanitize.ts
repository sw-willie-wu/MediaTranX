/**
 * agentSanitize — preserves the hard-won model-quirk fixes from the old
 * useAgentSSE.assembledAssistantMessage(), applied to @ag-ui/client newMessages.
 *
 * The SDK does NOT filter phantom empty-name tool calls (Bug #9) nor normalize
 * truncated/empty tool-call args in the final assembled message (spike SPIKE-2/3),
 * so we re-apply both here.
 */
import type { Message } from '@ag-ui/client'

export type ToolCall = { id: string; type: 'function'; function: { name: string; arguments: string } }
export interface SanitizedAssistant {
  id: string
  role: 'assistant'
  content: string
  toolCalls: ToolCall[]
}

/** Normalize a streamed tool-call `arguments` string to valid JSON-encoded object. */
export function normalizeToolCallArgs(raw: string): string {
  const trimmed = (raw ?? '').trim()
  if (!trimmed) return '{}'
  try {
    JSON.parse(trimmed)
    return trimmed
  } catch {
    return '{}'
  }
}

/** Return the LAST assistant message in the SDK newMessages (or undefined). */
export function pickAssistant(newMessages: Message[]): Message | undefined {
  for (let i = newMessages.length - 1; i >= 0; i--) {
    if (newMessages[i]?.role === 'assistant') return newMessages[i]
  }
  return undefined
}

/** Sanitize an SDK assistant message into our local committed-message shape. */
export function sanitizeAssistantMessage(raw: Message | undefined): SanitizedAssistant | null {
  if (!raw) return null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rawToolCalls: any[] = (raw as any).toolCalls ?? []
  const toolCalls: ToolCall[] = rawToolCalls
    .filter((tc) => tc?.function?.name && String(tc.function.name).trim())
    .map((tc) => ({
      id: tc.id ?? crypto.randomUUID(),
      type: 'function' as const,
      function: { name: tc.function.name, arguments: normalizeToolCallArgs(tc.function.arguments) },
    }))
  return {
    id: raw.id ?? crypto.randomUUID(),
    role: 'assistant' as const,
    // `Message` is a discriminated union; `content` widens to
    // string | Record | ContentArray[] | undefined (multimodal/activity msgs).
    // Assistant content is always a string when present — narrow defensively.
    content: typeof raw.content === 'string' ? raw.content : '',
    toolCalls,
  }
}
