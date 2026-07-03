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
import { getApiBase, apiFetch } from '@/composables/useApi'
import { sanitizeAssistantMessage, pickAssistant, type SanitizedAssistant, type ToolCall } from '@/composables/agentSanitize'
import { useAgentStore, type TransientBuffer, type TokenUsage } from '@/stores/agent'
import { useAgentSettingsStore } from '@/stores/agentSettings'
import { useAgentTools } from '@/composables/useAgentTools'
import { useActivePanel, type ActivePanelEntry } from '@/composables/useActivePanel'
import { useActiveView } from '@/composables/useActiveView'
import type { PanelAgentSchema } from '@/stores/panelRegistry'
import type { ViewHandle } from '@/stores/viewRegistry'
import { buildAgentStateSnapshot } from '@/composables/useAgentState'
import { routeForView } from '@/agent/agentNavCatalog'
import { useFilesStore } from '@/stores/files'
import { useToast } from '@/composables/useToast'
import i18n from '@/i18n'

// i18n resolver — static ESM import (browser has no `require`; the old lazy
// require() fell back to identity, so agent error codes rendered as raw keys).
function translate(key: string): string {
  return i18n.global.t(key)
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
  dispatch(
    toolCall: { id: string; function: { name: string; arguments: string } },
    ctx?: { signal?: AbortSignal },
  ): Promise<{ ok?: boolean; error?: string; [k: string]: unknown }>
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

/**
 * Resume-side defense: drop assistant tool_calls entries that have no matching
 * tool row, and drop orphan tool rows (no matching assistant call). An
 * unbalanced history would 400 OpenAI when re-sent verbatim on the next round
 * (see agent_service _msg_to_dict + the OpenAI Strict Tool Calling work).
 */
function sanitizeHistory(msgs: Message[]): Message[] {
  const toolRowIds = new Set(
    msgs.filter((m) => m.role === 'tool').map((m) => (m as Extract<Message, { role: 'tool' }>).toolCallId),
  )
  const keptCallIds = new Set<string>()
  const out: Message[] = []
  for (const m of msgs) {
    if (m.role === 'assistant') {
      const kept = (m.toolCalls ?? []).filter((tc) => toolRowIds.has(tc.id))
      for (const tc of kept) keptCallIds.add(tc.id)
      out.push(kept.length ? { ...m, toolCalls: kept } : { role: 'assistant', content: m.content })
    } else if (m.role === 'tool') {
      if (keptCallIds.has(m.toolCallId)) out.push(m)  // assistant always precedes its tool rows
    } else {
      out.push(m)
    }
  }
  return out
}

/**
 * Launder a value into a plain, structured-cloneable object tree.
 *
 * HttpAgent.runAgent() runs structuredClone() on its inputs (messages / state /
 * tools). Those inputs originate from Vue reactive stores (messages.value,
 * panel-derived tool schemas), and a reactive Proxy is NOT structured-cloneable
 * — the browser throws "could not be cloned". Our agent payloads are all
 * JSON-safe (strings / numbers / arrays / plain objects), so a JSON round-trip
 * is the simplest correct way to strip the reactive proxies at the SDK boundary.
 */
function toCloneable<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

/**
 * Map a received tool call → the banner action label key + args, so the runLoop
 * can announce "doing X" the moment the LLM's tool call arrives (before the tool
 * actually runs). Mirrors the i18n keys each dispatcher uses (useAgentTools).
 */
function bannerActionFor(tc: ToolCall): { key: string; args: Record<string, unknown> } {
  const name = tc.function.name
  let a: Record<string, unknown> = {}
  try { a = JSON.parse(tc.function.arguments || '{}') } catch { a = {} }
  const key = `agent.banner.act.${name}`
  switch (name) {
    case 'navigate_to': return { key, args: { route: a.route } }
    case 'select_subfunction': return { key, args: { name: a.name } }
    case 'load_file': return { key, args: { file_id: a.file_id } }
    case 'open_dropdown': return { key, args: { field: a.field } }
    case 'set_field': return { key, args: { field: a.field, value: String(a.value) } }
    case 'click_action': return { key, args: { name: a.name } }
    case 'get_task_status': return { key, args: { task_id: a.task_id } }
    default: return { key, args: {} } // click_execute, list_files
  }
}

// Bounded-1 nudge (Bug 1): when a round returns text only (no tool call) and the
// turn hasn't yet reached a terminal action, steer the model to actually emit the
// tool call it just described. One nudge per user turn; not rendered, not persisted.
const AGENT_NUDGE_TEXT =
  '如果剛才的請求還有尚未執行的操作，請直接呼叫對應的工具完成它；若已完成或只是在回答，簡短回覆即可，不必道歉或重複說明。'

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
  const toast = useToast()
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

  const currentSessionId = ref<string>(crypto.randomUUID())
  const threadId = ref<string>(currentSessionId.value)
  const messages = ref<Message[]>([])
  const isRunning = computed(() => store.isRunning)

  let agent: AgentLike | null = null
  let invalidFieldStrikes = 0
  let outerStop = false
  // Per-run abort handle. Created fresh at the top of each runLoop() (one per
  // user turn), aborted by cancelRun(). Its signal is threaded into
  // tools.dispatch so an already-started state-mutating tool can refuse to apply
  // its change when the user presses stop mid-dispatch.
  let runAbort: AbortController | null = null
  // Bug 1 nudge state (per user turn; reset in sendUserText/startNewSession/loadSession).
  let actedThisTurn = false    // set at dequeue of click_execute/click_action (approve OR cancel)
  let nudgedThisTurn = false   // cap: at most one nudge per user turn
  let pendingNudge: string | null = null  // consumed at the top of the next round's wire build
  let thisRoundIsNudge = false

  // ─── Public API ──────────────────────────────────────────────────

  async function sendUserText(text: string) {
    store.clearRunError()
    await commitMessage({ role: 'user', content: text })
    invalidFieldStrikes = 0
    outerStop = false
    actedThisTurn = false
    nudgedThisTurn = false
    pendingNudge = null
    // Reset the action label once per user turn (not per round): within a run
    // the banner keeps showing the latest tool action, only falling back to the
    // generic label at the very start before the first tool dispatches.
    store.setCurrentAction('', {})
    await runLoop()
  }

  function startNewSession() {
    // Non-destructive: leaves the prior conversation saved in the DB (reachable
    // from the session list). Starts a fresh thread with a new id.
    const id = crypto.randomUUID()
    currentSessionId.value = id
    threadId.value = id
    messages.value = []
    agent = null              // recreate with fresh threadId next run
    store.resetTokens()
    store.clearRunError()
    invalidFieldStrikes = 0
    outerStop = false
    actedThisTurn = false
    nudgedThisTurn = false
    pendingNudge = null
  }

  function cancelRun() {
    agent?.abortRun()                         // SDK surfaces abort as onRunErrorEvent{code:'abort'}
    runAbort?.abort()                         // trip the in-flight dispatch guard
    store.resolveAllPendingConfirms(false)    // m4
    outerStop = true                          // spec §3.4: cancel → loop break
  }

  /**
   * Persist one committed message to the session, best-effort. AWAITED (not
   * fire-and-forget): isRunning gates a second sendUserText, so there is only
   * ever one in-flight writer per session — seq has no race and lazy-create
   * can't double-create. On failure we warn and continue (in-memory messages
   * stay authoritative for the live session).
   */
  async function persistMessage(sessionId: string, msg: Message): Promise<void> {
    try {
      const body: Record<string, unknown> = { role: msg.role }
      if (msg.role === 'user') {
        body.content = msg.content
      } else if (msg.role === 'assistant') {
        body.content = msg.content
        if (msg.toolCalls && msg.toolCalls.length) body.tool_calls = msg.toolCalls
      } else if (msg.role === 'tool') {
        body.content = msg.content
        body.tool_call_id = msg.toolCallId
      } else {
        return  // tool_confirm / transient are never persisted
      }
      const res = await apiFetch(`/agent/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) console.warn(`[useAgent] persist failed: HTTP ${res.status}`)
    } catch (e) {
      console.warn('[useAgent] persist failed:', e)
    }
  }

  /** Push a committed message AND persist it. The single funnel for all 9 sites. */
  async function commitMessage(msg: Message): Promise<void> {
    messages.value.push(msg)
    await persistMessage(currentSessionId.value, msg)
  }

  /** Load a persisted session for resume. Throws on fetch failure (caller toasts). */
  async function loadSession(id: string): Promise<void> {
    const res = await apiFetch(`/agent/sessions/${id}/messages`)
    if (!res.ok) throw new Error(`loadSession failed: HTTP ${res.status}`)
    const data = (await res.json()) as { id: string; messages: Message[] }
    messages.value = sanitizeHistory(data.messages ?? [])
    currentSessionId.value = id
    threadId.value = id
    agent = null               // recreate HttpAgent for this thread id
    store.resetTokens()        // token counts aren't persisted; clear the running total
    store.clearRunError()
    invalidFieldStrikes = 0
    outerStop = false
    actedThisTurn = false
    nudgedThisTurn = false
    pendingNudge = null
  }

  /** Delete a persisted session. If it's the active one, start a fresh session. */
  async function deleteSession(id: string): Promise<void> {
    const res = await apiFetch(`/agent/sessions/${id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`deleteSession failed: HTTP ${res.status}`)
    if (id === currentSessionId.value) startNewSession()
  }

  // ─── Run loop ────────────────────────────────────────────────────

  async function runLoop() {
    runAbort = new AbortController()   // fresh per user turn; cancelRun() aborts it
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
        // toCloneable: HttpAgent structuredClones these inputs; strip Vue reactive proxies.
        agent.messages = toCloneable(mapMessagesToAgUi(messages.value))
        // Bug 1 nudge: append a one-shot steering user message to THIS round's wire
        // only. It never enters messages.value → not rendered, not persisted. `id` is
        // required by ag_ui BaseMessage (backend RunAgentInput pydantic-validates).
        thisRoundIsNudge = false
        if (pendingNudge) {
          ;(agent.messages as AgUiMessage[]).push(
            { id: crypto.randomUUID(), role: 'user', content: pendingNudge } as unknown as AgUiMessage,
          )
          pendingNudge = null
          thisRoundIsNudge = true
        }
        // Build the two-tier UI snapshot from live state, then launder the whole
        // `state` object through toCloneable — HttpAgent structuredClones state,
        // and snapshot is derived from reactive stores/getters. _createAgent has
        // NO router var; derive route from the active panel's viewId via the catalog.
        const ap = getActivePanel()
        const av = getActiveView()
        const filesStore = useFilesStore()
        const cur = filesStore.currentFile
        const viewId = ap ? ap.panelId.split('.')[0] : null
        const snapshot = buildAgentStateSnapshot({
          activePanel: ap
            ? { panelId: ap.panelId, schema: ap.schema, currentValues: ap.instance.getCurrentValues() }
            : null,
          currentRoute: viewId ? routeForView(viewId) : null,
          currentSubfunction:
            av?.currentFunction.value ?? (ap ? ap.panelId.split('.').slice(1).join('.') : null),
          files: filesStore.allFiles.map(f => ({
            id: f.id, name: f.originalName ?? f.name, kind: f.type,
          })),
          activeFile: cur ? { id: cur.id, name: cur.originalName ?? cur.name, kind: cur.type } : null,
        })
        agent.state = toCloneable({ agent_model_choice: settings.modelChoice, snapshot })

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
              // toCloneable: defensive — getTools() output is normally plain, but
              // launder at the SDK boundary so a future reactive-sourced field can't
              // silently reintroduce the structuredClone crash (messages is the
              // confirmed leak source; see toCloneable docblock).
              tools: toCloneable(tools.getTools(getActivePanel()?.schema ?? null, getActiveView())),
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
        if (runError) {                        // 4b: backend RUN_ERROR → friendly toast + transient in-conversation label
          store.clearTransient()
          const re = runError as { code?: string; message?: string }
          const code = re.code ?? 'agent.error.internal'
          const translated = translate(code)
          // Never surface a raw i18n key: fall back to the generic friendly message.
          const friendly = translated === code ? translate('agent.error.generic') : translated
          // Raw technical detail → log only (backend also logs server-side); never in the UI.
          console.error('[agent] RUN_ERROR', code, re.message ?? '')
          toast.show(friendly, { type: 'error', duration: 0 })
          store.setRunError(friendly)          // transient label below the last message (not persisted)
          outerStop = true
          break
        }
        if (caught && !result) {               // 4c: unexpected reject (no RUN_ERROR)
          store.clearTransient()
          console.error('[useAgent] runLoop error:', caught)
          await commitMessage({
            role: 'assistant',
            content: `[agent.error.internal] ${String(caught instanceof Error ? caught.message : caught)}`,
          })
          break
        }

        // ── 4d: success ──
        const assistant: SanitizedAssistant | null = sanitizeAssistantMessage(pickAssistant(result!.newMessages))
        store.addUsage(capturedUsage)
        store.clearTransient()

        // Announce the first tool action the moment it's received — BEFORE the
        // (networked) assistant-message persist below — so the banner reads
        // "doing X" while that round-trip happens, ahead of the tool running.
        const firstTc = assistant?.toolCalls?.[0]
        if (firstTc) {
          const ba = bannerActionFor(firstTc)
          store.setCurrentAction(ba.key, ba.args)
        }

        // R2-D: a nudge round that produced only text (no tool call) is redundant —
        // the real answer was the prior round. Suppress it (don't commit/render) so
        // the weird "sorry, I already called the tool" message never appears.
        // (transient already cleared by the store.clearTransient() just above — N2.)
        if (thisRoundIsNudge && (!assistant || assistant.toolCalls.length === 0)) {
          break
        }

        if (assistant) await commitMessage(assistant)

        unprocessedToolCalls = assistant ? [...assistant.toolCalls] : []
        if (unprocessedToolCalls.length === 0) {
          // Bug 1: a text-only round is normally terminal (matches Claude Code's
          // loop). Safety net for weak local models: if the turn hasn't reached a
          // terminal action yet, nudge once and re-run — the model either emits the
          // tool call it forgot, or replies again (then we terminate on the cap).
          if (!actedThisTurn && !nudgedThisTurn) {
            nudgedThisTurn = true
            pendingNudge = AGENT_NUDGE_TEXT
            continue
          }
          break
        }

        // ── Dispatch tool_calls (logic unchanged from original) ──
        while (unprocessedToolCalls.length > 0 && !outerStop) {
          const tc = unprocessedToolCalls[0]
          // M1: mark the turn as having reached a terminal action the moment such a
          // tool is dequeued — BEFORE the confirm decision — so a user-cancelled
          // confirm still suppresses the next-round nudge (no spurious re-pop).
          if (tc.function.name === 'click_execute' || tc.function.name === 'click_action') {
            actedThisTurn = true
          }
          const ap = getActivePanel()
          // Announce this tool at receive-time, before it runs (the first was
          // announced above; this covers the 2nd+ tools in a multi-call round).
          const ba = bannerActionFor(tc)
          store.setCurrentAction(ba.key, ba.args)

          if (settings.shouldConfirm({ name: tc.function.name, arguments: undefined }, ap?.schema ?? undefined)) {
            const approved = await pushConfirmCard(tc)
            if (!approved) {
              await commitMessage({ role: 'tool', toolCallId: tc.id, content: JSON.stringify({ user_cancelled: true }) })
              unprocessedToolCalls.shift()
              continue
            }
          }

          const dispatchResult = await tools.dispatch(tc, { signal: runAbort?.signal })
          await commitMessage({ role: 'tool', toolCallId: tc.id, content: JSON.stringify(dispatchResult) })
          unprocessedToolCalls.shift()

          if (dispatchResult.error === 'agent.error.invalid_field') {
            invalidFieldStrikes++
            if (invalidFieldStrikes >= 3) {
              for (const remaining of unprocessedToolCalls) {
                await commitMessage({ role: 'tool', toolCallId: remaining.id, content: JSON.stringify({ skipped: 'too_many_strikes' }) })
              }
              unprocessedToolCalls = []
              outerStop = true
              break
            }
          }
        }

        // Cancel mid-round leaves the inner loop (outerStop) with tool calls that
        // never got a tool row. Every assistant tool_call needs a matching tool
        // response or the next same-session round unbalances the history and
        // 400s (mapMessagesToAgUi doesn't sanitize; sanitizeHistory only runs on
        // resume). Synth an aborted row for each remaining call. The strikes path
        // above already empties the array, and a successful round drains it via
        // shift(), so this only fires on cancel.
        if (unprocessedToolCalls.length > 0) {
          for (const rem of unprocessedToolCalls) {
            await commitMessage({ role: 'tool', toolCallId: rem.id, content: JSON.stringify({ error: 'agent.error.aborted' }) })
          }
          unprocessedToolCalls = []
        }
      } catch (e: unknown) {
        // Reachable only from the tool-dispatch phase (runAgent errors captured
        // into `caught` above). Mirror legacy: synth skipped for remaining tool calls.
        for (const tc of unprocessedToolCalls) {
          await commitMessage({ role: 'tool', toolCallId: tc.id, content: JSON.stringify({ skipped: 'cancelled' }) })
        }
        if (!(e instanceof Error && e.name === 'AbortError')) {
          console.error('[useAgent] runLoop dispatch error:', e)
          await commitMessage({
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

  return { threadId, currentSessionId, messages, isRunning, sendUserText, cancelRun, startNewSession, loadSession, deleteSession }
}
