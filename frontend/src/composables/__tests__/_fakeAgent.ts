/* eslint-disable @typescript-eslint/no-explicit-any */
import { vi } from 'vitest'
import type { AgentLike } from '@/composables/useAgent'

export interface FakeRoundScript {
  textDeltas?: string[]
  toolCalls?: Array<{ id: string; name: string; args: string }>
  usage?: { promptTokens: number; completionTokens: number }
  /** fire onRunErrorEvent then reject runAgent (mimics conformant lone RUN_ERROR) */
  error?: { code?: string; message: string }
  /** block until abortRun() is called, then fire code:'abort' onRunErrorEvent and reject */
  blockUntilAbort?: boolean
  /** override the assembled assistant message */
  newMessages?: any[]
}

export interface FakeAgentHandle {
  factory: (cfg: { url: string; threadId?: string }) => AgentLike
  agent: AgentLike & { runAgent: ReturnType<typeof vi.fn>; abortRun: ReturnType<typeof vi.fn> }
  /** params captured per runAgent call (params.tools etc.) */
  calls: Array<{ params: any; messagesIn: any[] }>
}

/**
 * Build a fake AgentLike whose runAgent(params, subscriber) fires SDK-shaped
 * subscriber callbacks and resolves with SDK-shaped { result, newMessages }.
 * scriptFn(round) returns the script for that 0-based round.
 */
export function makeFakeAgent(scriptFn: (round: number) => FakeRoundScript): FakeAgentHandle {
  let round = 0
  const calls: FakeAgentHandle['calls'] = []
  let abortResolve: (() => void) | null = null

  const agent: any = {
    messages: [] as any[],
    state: {} as Record<string, unknown>,
    abortRun: vi.fn(() => { abortResolve?.() }),
    runAgent: vi.fn(async (params: any, subscriber: any) => {
      const script = scriptFn(round)
      round += 1
      calls.push({ params, messagesIn: [...agent.messages] })

      for (const d of script.textDeltas ?? []) {
        subscriber?.onTextMessageContentEvent?.({ event: { messageId: 'm1', delta: d } })
      }
      for (const tc of script.toolCalls ?? []) {
        subscriber?.onToolCallStartEvent?.({ event: { toolCallId: tc.id, toolCallName: tc.name, parentMessageId: 'm1' } })
        subscriber?.onToolCallArgsEvent?.({ event: { toolCallId: tc.id, delta: tc.args } })
      }

      if (script.blockUntilAbort) {
        await new Promise<void>((r) => { abortResolve = r })
        subscriber?.onRunErrorEvent?.({ event: { code: 'abort', message: 'Request aborted' } })
        throw new Error('AGUIError: aborted')
      }

      if (script.error) {
        subscriber?.onRunErrorEvent?.({ event: { code: script.error.code, message: script.error.message } })
        // Conformant lone RUN_ERROR (or non-conformant trailing RUN_FINISHED) both reject.
        throw new Error('AGUIError: run errored')
      }

      subscriber?.onRunFinishedEvent?.({ event: { usage: script.usage } })

      const newMessages = script.newMessages ?? [{
        id: 'm1',
        role: 'assistant',
        content: (script.textDeltas ?? []).join(''),
        toolCalls: (script.toolCalls ?? []).map((tc) => ({
          id: tc.id, type: 'function', function: { name: tc.name, arguments: tc.args },
        })),
      }]
      return { result: undefined, newMessages }
    }),
  }

  return { factory: () => agent as AgentLike, agent, calls }
}
