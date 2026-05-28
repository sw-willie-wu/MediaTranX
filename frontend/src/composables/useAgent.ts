/**
 * useAgent — central agent orchestrator composable.
 *
 * Drives the multi-round conversation loop on top of @ag-ui/client HttpAgent:
 *   agent.runAgent(round) → newMessages → sanitize → tool dispatch → next round
 *
 * Key design decisions:
 * - M16: transient buffer prevents orphan UI text on cancel. The AgentSubscriber
 *   callbacks write to the transient buffer (not directly to messages.value).
 *   Committed (from sanitized newMessages) on clean return; discarded on cancel/error.
 * - Cancel: cancelRun() → agent.abortRun(). The SDK surfaces abort as
 *   onRunErrorEvent{code:'abort'} (NOT a thrown AbortError), so we detect it in
 *   the subscriber and treat as a silent cancel (spec §2.7-1).
 * - Error: backend RUN_ERROR causes runAgent to reject; onRunErrorEvent fires
 *   BEFORE the reject, so we capture {code,message} and handle it after await,
 *   surviving both resolve and reject (spec §4 unified post-await handling).
 * - Singleton pattern: all callers share the same instance. _resetAgent() in tests.
 */

import { ref, computed, getCurrentInstance } from 'vue'
import { HttpAgent } from '@ag-ui/client'
import type { Message as AgUiMessage, RunAgentResult, AgentSubscriber } from '@ag-ui/client'
import { getApiBase } from '@/composables/useApi'
import { sanitizeAssistantMessage, pickAssistant, type SanitizedAssistant, type ToolCall } from '@/composables/agentSanitize'
import { useAgentStore, type TransientBuffer, type TokenUsage } from '@/stores/agent'
import { useAgentSettingsStore } from '@/stores/agentSettings'
import { useAgentTools } from '@/composables/useAgentTools'
import { useActivePanel, type ActivePanelEntry } from '@/composables/useActivePanel'
import { useActiveView } from '@/composables/useActiveView'
import type { PanelAgentSchema } from '@/stores/panelRegistry'
import type { ViewHandle } from '@/stores/viewRegistry'

// i18n.global.t lazy resolve (unchanged from original).
let _t: ((k: string) => string) | null = null
function translate(key: string): string {
  if (_t === null) {
    try {
      // @ts-expect-error — require() available in Vitest (node) + Vite (cjs interop)
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const mod = require('@/i18n')
      _t = (mod.default ?? mod).global.t
    } catch {
      _t = (k: string) => k
    }
  }
  return _t!(key)
}

// ─── Public types ──────────────────────────────────────────────────────────────

export type ToolCallEntry = { id: string; function: { name: string; arguments: string } }
export type ToolConfirmEntry = { id: string; function: { name: string; arguments: string }; status?: string }

export type Message =
  | { id?: string; role: 'user'; content: string }
  | { id?: string; role: 'assistant'; content: string; toolCalls?: ToolCallEntry[] }
  | { id?: string; role: 'tool'; content: string; toolCallId: string }
  | { id?: string; role: 'tool_confirm'; toolCall: ToolConfirmEntry; status: 'pending' }

/** Minimal slice of HttpAgent we depend on — lets tests inject a fake. */
export interface AgentLike {
  messages: AgUiMessage[]
  state: Record<string, unknown>
  runAgent(
    params: { runId?: string; tools?: unknown[]; context?: unknown[]; forwardedProps?: Record<string, unknown> },
    subscriber?: AgentSubscriber,
  ): Promise<RunAgentResult>
  abortRun(): void
}

export interface ToolsApi {
  TOOLS: Array<{ name: string; description: string; parameters: object }>
  getTools: (activePanelSchema?: PanelAgentSchema | null, activeViewHandle?: ViewHandle | null) => Array<{ name: string; description: string; parameters: object }>
  dispatch(toolCall: { id: string; function: { name: string; arguments: string } }): Promise<{ ok?: boolean; error?: string; [k: string]: unknown }>
}

export interface UseAgentDeps {
  tools?: ToolsApi
  /** Override agent construction for tests. Real impl: (cfg) => new HttpAgent(cfg). */
  agentFactory?: (cfg: { url: string; threadId?: string }) => AgentLike
  activePanelRef?: () => ActivePanelEntry | null
}

// ─── Map our Message[] → SDK AgUiMessage[] (per-round input vehicle) ────────────

function mapMessagesToAgUi(msgs: Message[]): AgUiMessage[] {
  return msgs
    .filter((m) => m.role !== 'tool_confirm')
    .map((m) => {
      if (m.role === 'assistant') {
        return {
          id: m.id ?? crypto.randomUUID(),
          role: 'assistant' as const,
          content: m.content ?? '',
          toolCalls: (m.toolCalls ?? []).map((tc) => ({
            id: tc.id, type: 'function' as const, function: tc.function,
          })),
        }
      }
      if (m.role === 'tool') {
        return { id: m.id ?? crypto.randomUUID(), role: 'tool' as const, toolCallId: m.toolCallId, content: m.content }
      }
      if (m.role === 'user') {
        return { id: m.id ?? crypto.randomUUID(), role: 'user' as const, content: m.content }
      }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const _m = m as any
      return { id: _m.id ?? crypto.randomUUID(), role: String(_m.role), content: '' }
    }) as unknown as AgUiMessage[]
}

// ─── Module-level singleton ────────────────────────────────────────────────────

let _instance: ReturnType<typeof _createAgent> | null = null

export function _resetAgent(): void {
  _instance = null
}

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
  const store = useAgentStore()
  const tools = deps.tools ?? useAgentTools()
  const makeAgent = deps.agentFactory ?? ((cfg: { url: string; threadId?: string }) => new HttpAgent(cfg) as unknown as AgentLike)

  let apComputed: ReturnType<typeof useActivePanel> | null = null
  let avComputed: ReturnType<typeof useActiveView> | null = null
  if (deps.activePanelRef === undefined && getCurrentInstance() !== null) {
    try { apComputed = useActivePanel() } catch { apComputed = null }
    try { avComputed = useActiveView() } catch { avComputed = null }
  }
  const getActivePanel = deps.activePanelRef ?? (() => apComputed?.value ?? null)
  const getActiveView = () => avComputed?.value ?? null

  const threadId = ref<string>(crypto.randomUUID())
  const messages = ref<Message[]>([])
  const isRunning = computed(() => store.isRunning)

  let agent: AgentLike | null = null
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
    agent = null              // recreate with fresh threadId next run
    store.resetTokens()
    invalidFieldStrikes = 0
    outerStop = false
  }

  function cancelRun() {
    agent?.abortRun()                         // SDK surfaces abort as onRunErrorEvent{code:'abort'}
    store.resolveAllPendingConfirms(false)    // m4
    outerStop = true                          // spec §3.4: cancel → loop break
  }

  // ─── Run loop ────────────────────────────────────────────────────

  async function runLoop() {
    while (!outerStop) {
      store.start()
      const transient: TransientBuffer = { messageId: '', text: '', toolCallsBuf: new Map() }
      store.setTransient(transient)

      let cancelled = false
      let runError: { code?: string; message?: string } | null = null
      let capturedUsage: TokenUsage | undefined
      let result: RunAgentResult | null = null
      let caught: unknown = null
      // Sanitized tool calls carry `type:'function'` (ToolCall) so they can be
      // passed straight to tools.dispatch (which requires the full shape).
      let unprocessedToolCalls: ToolCall[] = []

      try {
        if (!agent) {
          agent = makeAgent({ url: `${getApiBase()}/agent/run`, threadId: threadId.value })
        }
        agent.messages = mapMessagesToAgUi(messages.value)
        agent.state = { agent_model_choice: settings.modelChoice }

        const subscriber: AgentSubscriber = {
          onTextMessageContentEvent: ({ event }) => {
            transient.messageId = event.messageId
            transient.text += event.delta
          },
          onToolCallStartEvent: ({ event }) => {
            transient.toolCallsBuf.set(event.toolCallId, { name: event.toolCallName, args: '' })
          },
          onToolCallArgsEvent: ({ event }) => {
            const slot = transient.toolCallsBuf.get(event.toolCallId)
            if (slot) slot.args += event.delta
          },
          onRunFinishedEvent: ({ event }) => {
            // RunFinishedEvent schema is "passthrough"; usage rides as an extra.
            capturedUsage = (event as { usage?: TokenUsage }).usage
          },
          onRunErrorEvent: ({ event }) => {
            if (event.code === 'abort') cancelled = true
            else runError = { code: event.code, message: event.message }
          },
        }

        try {
          result = await agent.runAgent(
            {
              runId: crypto.randomUUID(),
              tools: tools.getTools(getActivePanel()?.schema ?? null, getActiveView()),
              context: [],
              forwardedProps: {},
            },
            subscriber,
          )
        } catch (e) {
          caught = e   // error/abort path: runAgent rejects; rely on captured state
        }

        // ── Unified post-await handling (survives resolve & reject) ──
        if (cancelled) {                       // 4a: silent cancel
          store.clearTransient()
          outerStop = true
          break
        }
        if (runError) {                        // 4b: backend RUN_ERROR
          store.clearTransient()
          // Cast needed: TS can't narrow a closure-mutated `let` across the
          // await, collapsing it to `never` at this guard. Extract once.
          const re = runError as { code?: string; message?: string }
          const code = re.code ?? 'agent.error.internal'
          const translated = translate(code)
          const friendly = translated === code ? code : translated
          const suffix = re.message ? ` (${re.message})` : ''
          messages.value.push({ role: 'assistant', content: `${friendly}${suffix}` })
          outerStop = true
          break
        }
        if (caught && !result) {               // 4c: unexpected reject (no RUN_ERROR)
          store.clearTransient()
          console.error('[useAgent] runLoop error:', caught)
          messages.value.push({
            role: 'assistant',
            content: `[agent.error.internal] ${String(caught instanceof Error ? caught.message : caught)}`,
          })
          break
        }

        // ── 4d: success ──
        const assistant: SanitizedAssistant | null = sanitizeAssistantMessage(pickAssistant(result!.newMessages))
        store.addUsage(capturedUsage)
        store.clearTransient()
        if (assistant) messages.value.push(assistant)

        unprocessedToolCalls = assistant ? [...assistant.toolCalls] : []
        if (unprocessedToolCalls.length === 0) break

        // ── Dispatch tool_calls (logic unchanged from original) ──
        while (unprocessedToolCalls.length > 0 && !outerStop) {
          const tc = unprocessedToolCalls[0]
          const ap = getActivePanel()

          if (settings.shouldConfirm({ name: tc.function.name, arguments: undefined }, ap?.schema ?? undefined)) {
            const approved = await pushConfirmCard(tc)
            if (!approved) {
              messages.value.push({ role: 'tool', toolCallId: tc.id, content: JSON.stringify({ user_cancelled: true }) })
              unprocessedToolCalls.shift()
              continue
            }
          }

          const dispatchResult = await tools.dispatch(tc)
          messages.value.push({ role: 'tool', toolCallId: tc.id, content: JSON.stringify(dispatchResult) })
          unprocessedToolCalls.shift()

          if (dispatchResult.error === 'agent.error.invalid_field') {
            invalidFieldStrikes++
            if (invalidFieldStrikes >= 3) {
              for (const remaining of unprocessedToolCalls) {
                messages.value.push({ role: 'tool', toolCallId: remaining.id, content: JSON.stringify({ skipped: 'too_many_strikes' }) })
              }
              unprocessedToolCalls = []
              outerStop = true
              break
            }
          }
        }
      } catch (e: unknown) {
        // Reachable only from the tool-dispatch phase (runAgent errors captured
        // into `caught` above). Mirror legacy: synth skipped for remaining tool calls.
        for (const tc of unprocessedToolCalls) {
          messages.value.push({ role: 'tool', toolCallId: tc.id, content: JSON.stringify({ skipped: 'cancelled' }) })
        }
        if (!(e instanceof Error && e.name === 'AbortError')) {
          console.error('[useAgent] runLoop dispatch error:', e)
          messages.value.push({
            role: 'assistant',
            content: `[agent.error.internal] ${String(e instanceof Error ? e.message : e)}`,
          })
        }
        break
      } finally {
        store.stop()   // ★ N1: isRunning reset on every exit path
      }
    }
  }

  // ─── ConfirmCard handling (m4 pendingConfirms) — unchanged ────────

  async function pushConfirmCard(tc: { id: string; function: { name: string; arguments: string } }): Promise<boolean> {
    messages.value.push({ role: 'tool_confirm', toolCall: tc, status: 'pending' })
    return new Promise<boolean>((resolve) => {
      store.addPendingConfirm(resolve)
    })
  }

  return { threadId, messages, isRunning, sendUserText, cancelRun, clearHistory }
}
