/**
 * useAgent — central agent orchestrator composable.
 *
 * Drives the multi-round conversation loop:
 *   streamRun → assistant message → tool dispatch → tool results → next round
 *
 * Key design decisions:
 * - M16: transient buffer prevents orphan UI text on cancel. onTextChunk /
 *   onToolCallChunk write to the transient buffer (not directly to
 *   messages.value). The buffer is committed on clean streamRun return and
 *   discarded on cancel/error.
 * - m4: cancelRun() resolves all pending confirm cards with false so the
 *   runLoop can break.
 * - useActivePanel is Task 3.1/3.2. Until then, accept activePanelRef as
 *   injectable dep with a default of () => null.
 * - Singleton pattern: all callers (ChatBubble, AgentRunBanner, etc.) share
 *   the same instance so cancelRun() and isRunning are always in sync.
 *   Tests call _resetAgent() in beforeEach for isolation.
 */

import { ref, computed } from 'vue'
import { streamRun, type AssistantMessage } from '@/composables/useAgentSSE'
import { useAgentStore, type TransientBuffer } from '@/stores/agent'
import { useAgentSettingsStore } from '@/stores/agentSettings'
import { useAgentTools } from '@/composables/useAgentTools'

// ─── Public types ──────────────────────────────────────────────────────────────

export type Message =
  | { id?: string; role: 'user'; content: string }
  | { id?: string; role: 'assistant'; content: string; toolCalls?: any[] }
  | { id?: string; role: 'tool'; content: string; toolCallId: string }
  | { id?: string; role: 'tool_confirm'; toolCall: any; status: 'pending' }  // client-only (m13)

// ─── Injectable deps interface ─────────────────────────────────────────────────

/**
 * Minimal ToolsApi — Task 3.6 will provide the real implementation.
 * For Task 2.3 we define the interface here so tests can inject fakes.
 */
export interface ToolsApi {
  TOOLS: Array<{ name: string; description: string; parameters: object }>
  dispatch(toolCall: { id: string; function: { name: string; arguments: string } }): Promise<{ ok?: boolean; error?: string; [k: string]: any }>
}

export interface UseAgentDeps {
  /** Injectable for testing. Real impl is Task 3.6 useAgentTools. */
  tools?: ToolsApi
  /** Override streamRun for tests. */
  streamRunFn?: typeof streamRun
  /** Override active panel resolution for tests. Task 3.2 wires the real one. */
  activePanelRef?: () => { schema: any } | null
}

// ─── Module-level singleton ────────────────────────────────────────────────────

let _instance: ReturnType<typeof _createAgent> | null = null

/**
 * Reset the singleton — for tests only.
 * Call in beforeEach to get a fresh instance per test.
 */
export function _resetAgent(): void {
  _instance = null
}

// ─── Singleton accessor ────────────────────────────────────────────────────────

/**
 * Returns the shared agent instance.
 * First caller may pass deps (e.g. in tests); subsequent callers get the
 * cached instance (deps ignored with a console.warn).
 */
export function useAgent(deps: UseAgentDeps = {}): ReturnType<typeof _createAgent> {
  if (!_instance) {
    _instance = _createAgent(deps)
  } else if (Object.keys(deps).length > 0) {
    console.warn('[useAgent] called with deps but instance already exists; ignoring deps')
  }
  return _instance
}

// ─── Internal factory ─────────────────────────────────────────────────────────

function _createAgent(deps: UseAgentDeps = {}) {
  const settings = useAgentSettingsStore()
  const store    = useAgentStore()
  const tools    = deps.tools ?? useAgentTools()
  const runStream = deps.streamRunFn ?? streamRun
  const getActivePanel = deps.activePanelRef ?? (() => null)

  const threadId = ref<string>(crypto.randomUUID())
  const messages = ref<Message[]>([])
  const isRunning = computed(() => store.isRunning)

  let abortCtl: AbortController | null = null
  let invalidFieldStrikes = 0
  let outerStop = false

  // ─── Public API ──────────────────────────────────────────────────

  async function sendUserText(text: string) {
    messages.value.push({ role: 'user', content: text })
    invalidFieldStrikes = 0
    outerStop = false
    await runLoop()
  }

  function clearHistory() {
    messages.value = []
    threadId.value = crypto.randomUUID()
    store.resetTokens()
    invalidFieldStrikes = 0
    outerStop = false
  }

  function cancelRun() {
    abortCtl?.abort()
    store.resolveAllPendingConfirms(false)   // m4: reject all waiting confirm cards
    outerStop = true   // spec §3.4: cancel → loop break, not just current SSE
  }

  // ─── Run loop ────────────────────────────────────────────────────

  async function runLoop() {
    while (!outerStop) {
      abortCtl = new AbortController()
      store.start()

      // M16: transient buffer for streamed text + tool_calls.
      // onTextChunk / onToolCallChunk write here, NOT to messages.value.
      // Commit on clean streamRun return; discard on cancel/error.
      const transient: TransientBuffer = {
        messageId: '',
        text: '',
        toolCallsBuf: new Map<string, { name: string; args: string }>(),
      }
      store.setTransient(transient)

      let assistantMsg: AssistantMessage | null = null
      let unprocessedToolCalls: Array<{ id: string; type: 'function'; function: { name: string; arguments: string } }> = []

      try {
        assistantMsg = await runStream({
          threadId: threadId.value,
          runId: crypto.randomUUID(),
          messages: messages.value
            .filter(m => m.role !== 'tool_confirm')
            .map(m => {
              if (m.role === 'assistant') {
                return {
                  id: m.id ?? crypto.randomUUID(),
                  role: 'assistant' as const,
                  content: (m as any).content ?? '',
                  toolCalls: (m as any).toolCalls ?? [],
                }
              }
              if (m.role === 'tool') {
                return {
                  id: m.id ?? crypto.randomUUID(),
                  role: 'tool' as const,
                  toolCallId: (m as any).toolCallId,
                  content: (m as any).content,
                }
              }
              if (m.role === 'user') {
                return {
                  id: m.id ?? crypto.randomUUID(),
                  role: 'user' as const,
                  content: (m as any).content,
                }
              }
              // unreachable per filter above (tool_confirm filtered out)
              return { id: (m as any).id ?? crypto.randomUUID(), role: (m as any).role as string, content: '' }
            }),
          tools: tools.TOOLS,
          state: { agent_model_choice: settings.modelChoice },
          signal: abortCtl.signal,
          onTextChunk: (e) => {
            transient.messageId = e.messageId
            transient.text += e.delta
          },
          onToolCallChunk: (e) => {
            const slot = transient.toolCallsBuf.get(e.toolCallId) ?? { name: e.toolCallName, args: '' }
            slot.args += e.delta
            if (e.toolCallName) slot.name = e.toolCallName
            transient.toolCallsBuf.set(e.toolCallId, slot)
          },
          onRunFinished: (e) => store.addUsage(e.usage),
          onError: (e) => {
            // RUN_ERROR from backend — record as assistant message and stop the loop
            messages.value.push({ role: 'assistant', content: `[${e.code}] ${e.message}` })
            outerStop = true
          },
        })

        // M16: clean return → commit transient to messages (unless RUN_ERROR set outerStop)
        if (!outerStop) {
          messages.value.push(assistantMsg)
        }
        store.clearTransient()
        unprocessedToolCalls = outerStop ? [] : [...(assistantMsg.toolCalls ?? [])]

        if (outerStop) break  // RUN_ERROR set outerStop above

        if (unprocessedToolCalls.length === 0) break

        // ── Dispatch tool_calls ─────────────────────────────────────
        while (unprocessedToolCalls.length > 0 && !outerStop) {
          const tc = unprocessedToolCalls[0]
          const ap = getActivePanel()

          if (settings.shouldConfirm(tc as any, ap?.schema ?? null)) {
            const approved = await pushConfirmCard(tc)
            if (!approved) {
              messages.value.push({
                role: 'tool',
                toolCallId: tc.id,
                content: JSON.stringify({ user_cancelled: true }),
              })
              unprocessedToolCalls.shift()
              continue
            }
          }

          const result = await tools.dispatch(tc)
          messages.value.push({
            role: 'tool',
            toolCallId: tc.id,
            content: JSON.stringify(result),
          })
          unprocessedToolCalls.shift()

          if (result.error === 'agent.error.invalid_field') {
            invalidFieldStrikes++
            if (invalidFieldStrikes >= 3) {
              // M16-INCOMPLETE-fix: synth skipped results for all remaining tool calls
              for (const remaining of unprocessedToolCalls) {
                messages.value.push({
                  role: 'tool',
                  toolCallId: remaining.id,
                  content: JSON.stringify({ skipped: 'too_many_strikes' }),
                })
              }
              unprocessedToolCalls = []
              outerStop = true
              break
            }
          }
        }
      } catch (e: any) {
        // M16: two sub-cases depending on whether streamRun completed
        if (assistantMsg) {
          // streamRun returned cleanly; error came from tool dispatch
          for (const tc of unprocessedToolCalls) {
            messages.value.push({
              role: 'tool',
              toolCallId: tc.id,
              content: JSON.stringify({ skipped: 'cancelled' }),
            })
          }
        } else {
          // streamRun threw mid-stream → discard transient (no assistant message added)
          store.clearTransient()
        }

        if (e?.name === 'AbortError') break

        // Non-abort error: log and break
        console.error('[useAgent] runLoop error:', e)
        messages.value.push({
          role: 'assistant',
          content: `[agent.error.internal] ${String(e?.message ?? e)}`,
        })
        break
      } finally {
        store.stop()
        abortCtl = null
      }
    }
  }

  // ─── ConfirmCard handling (m4 pendingConfirms) ────────────────────

  /**
   * Push a tool_confirm card to the message list and await user decision.
   * When the user clicks the card, ConfirmCard.vue calls
   * store.removePendingConfirm + resolves the promise.
   * cancelRun() calls store.resolveAllPendingConfirms(false) which iterates
   * the Set and resolves every waiting promise.
   */
  async function pushConfirmCard(tc: { id: string; function: { name: string; arguments: string } }): Promise<boolean> {
    messages.value.push({ role: 'tool_confirm', toolCall: tc, status: 'pending' })
    return new Promise<boolean>((resolve) => {
      store.addPendingConfirm(resolve)
    })
  }

  return {
    threadId,
    messages,
    isRunning,
    sendUserText,
    cancelRun,
    clearHistory,
  }
}
