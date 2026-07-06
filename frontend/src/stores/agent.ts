/**
 * Agent Runtime Store
 *
 * 管理 agent 執行期間的狀態：isRunning、currentAction、pendingConfirms、
 * threadTokens、transient streaming buffer。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface ActionKey {
  key: string              // i18n key, e.g. 'agent.banner.act.navigate_to'
  args: Record<string, unknown>  // i18n args, e.g. { route: '/video' }
}

export interface TokenUsage {
  promptTokens?: number
  completionTokens?: number
}

export interface TransientBuffer {
  messageId: string
  text: string
  toolCallsBuf: Map<string, { name: string; args: string }>
}

export type ConfirmResolver = (approved: boolean) => void

export const useAgentStore = defineStore('agent', () => {
  const isRunning = ref(false)
  const currentAction = ref<ActionKey>({ key: '', args: {} })
  const pendingConfirms = ref<Set<ConfirmResolver>>(new Set())

  // M21 B4 aggregation rule:
  //   prompt  = REPLACE  (each round re-sends full history, so promptTokens
  //                       already includes all prior turns)
  //   completion = ACCUMULATE (only the new completion is sent each round)
  const threadTokens = ref<{ prompt: number; completion: number }>({ prompt: 0, completion: 0 })
  const transient = ref<TransientBuffer | null>(null)
  const runError = ref<string | null>(null)

  // ─── Lifecycle ────────────────────────────────────────────────
  function start() {
    isRunning.value = true
  }

  function stop() {
    isRunning.value = false
  }

  // ─── Action banner ────────────────────────────────────────────
  function setCurrentAction(key: string, args: Record<string, unknown> = {}) {
    currentAction.value = { key, args }
  }

  // ─── Token accounting ─────────────────────────────────────────
  function addUsage(usage: TokenUsage | undefined) {
    if (!usage) return
    threadTokens.value = {
      prompt: usage.promptTokens ?? threadTokens.value.prompt,               // REPLACE
      completion: threadTokens.value.completion + (usage.completionTokens ?? 0), // ACCUMULATE
    }
  }

  function resetTokens() {
    threadTokens.value = { prompt: 0, completion: 0 }
  }

  // ─── Transient streaming buffer ───────────────────────────────
  function setTransient(buf: TransientBuffer) {
    transient.value = buf
  }

  function clearTransient() {
    transient.value = null
  }

  // ─── Transient run-error label ────────────────────────────────────
  function setRunError(msg: string) {
    runError.value = msg
  }

  function clearRunError() {
    runError.value = null
  }

  // ─── Pending confirms (tool-call approval cards) ──────────────
  function addPendingConfirm(r: ConfirmResolver) {
    // Reassign-Set pattern: always create new Set for Vue reactivity
    pendingConfirms.value = new Set([...pendingConfirms.value, r])
  }

  function removePendingConfirm(r: ConfirmResolver) {
    const next = new Set(pendingConfirms.value)
    next.delete(r)
    pendingConfirms.value = next
  }

  function resolveAllPendingConfirms(approved: boolean) {
    // m4: on cancelRun, resolve every awaiting confirm card
    const resolvers = Array.from(pendingConfirms.value)
    pendingConfirms.value = new Set()
    for (const r of resolvers) r(approved)
  }

  return {
    // state
    isRunning,
    currentAction,
    pendingConfirms,
    threadTokens,
    transient,
    runError,
    // lifecycle
    start,
    stop,
    // banner
    setCurrentAction,
    // tokens
    addUsage,
    resetTokens,
    // transient
    setTransient,
    clearTransient,
    // run-error label
    setRunError,
    clearRunError,
    // confirms
    addPendingConfirm,
    removePendingConfirm,
    resolveAllPendingConfirms,
  }
})
