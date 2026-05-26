/**
 * Agent Settings Store  (§6.7)
 *
 * 使用者偏好，持久化至 localStorage。
 *
 * policy:
 *   'auto'     — 白名單內自動批准，否則自動拒絕（無彈窗）
 *   'ask_all'  — 每次都問
 *   'custom'   — autoWhitelist 自動批准，alwaysAsk 彈窗，其餘拒絕
 *
 * m2 reassign-Set pattern:
 *   每個 Set mutator 一律 `xx.value = new Set(...)` 而非 `xx.value.add()`，
 *   確保 Vue reactivity system 偵測到變更。
 *
 * m3 migration:
 *   hydrate 時 whitelist = union(stored, DEFAULTS) - userRemovedTools，
 *   讓新版本加入的預設工具在已有設定的使用者上也能生效，
 *   但不強迫還原使用者明確移除的工具。
 */
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

// ─── Default whitelists ───────────────────────────────────────────────────────

/** 預設自動批准的 7 個工具 */
export const DEFAULT_AUTO_WHITELIST: ReadonlySet<string> = new Set([
  'navigate_to',
  'get_panel_state',
  'set_field',
  'open_field',
  'get_view_state',
  'set_view_function',
  'invoke_action',
])

/** 預設永遠詢問的 2 個工具 */
export const DEFAULT_ALWAYS_ASK: ReadonlySet<string> = new Set([
  'execute',
  'add_file',
])

export const AGENT_SETTINGS_KEY = 'agent_settings'

// ─── Types ────────────────────────────────────────────────────────────────────

export type AgentPolicy = 'auto' | 'ask_all' | 'custom'

export interface ToolCallLike {
  name: string
  arguments?: Record<string, unknown>
}

export interface PanelSchemaLike {
  execute?: { requiresConfirm: boolean } | null
}

interface StoredSettings {
  policy?: AgentPolicy
  autoWhitelist?: string[]
  alwaysAsk?: string[]
  userRemovedTools?: string[]
  modelChoice?: string
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useAgentSettingsStore = defineStore('agentSettings', () => {
  const policy = ref<AgentPolicy>('auto')
  const autoWhitelist = ref<Set<string>>(new Set(DEFAULT_AUTO_WHITELIST))
  const alwaysAsk = ref<Set<string>>(new Set(DEFAULT_ALWAYS_ASK))
  // m3: tracks which default tools the user explicitly removed, so hydrate
  // can skip re-adding them when new defaults are introduced in future versions.
  const userRemovedTools = ref<Set<string>>(new Set())
  const modelChoice = ref<string>('')

  // ─── Persistence ────────────────────────────────────────────────────────────

  function persist() {
    const stored: StoredSettings = {
      policy: policy.value,
      autoWhitelist: Array.from(autoWhitelist.value),
      alwaysAsk: Array.from(alwaysAsk.value),
      userRemovedTools: Array.from(userRemovedTools.value),
      modelChoice: modelChoice.value,
    }
    localStorage.setItem(AGENT_SETTINGS_KEY, JSON.stringify(stored))
  }

  /** Hydrate from localStorage.
   *
   * m3 migration logic for autoWhitelist:
   *   result = union(storedWhitelist, DEFAULT_AUTO_WHITELIST) - userRemovedTools
   *
   * This ensures:
   * - New defaults added in future versions appear for existing users.
   * - Tools the user explicitly removed are NOT re-added.
   */
  function hydrate() {
    const raw = localStorage.getItem(AGENT_SETTINGS_KEY)
    if (!raw) return  // no stored data → keep defaults

    let stored: StoredSettings
    try {
      stored = JSON.parse(raw) as StoredSettings
    } catch {
      return  // malformed JSON → keep defaults
    }

    if (stored.policy) policy.value = stored.policy
    if (stored.modelChoice !== undefined) modelChoice.value = stored.modelChoice

    const storedRemoved = new Set<string>(stored.userRemovedTools ?? [])
    userRemovedTools.value = storedRemoved

    // m3: union(stored, DEFAULTS) - userRemovedTools
    const storedWhitelist = new Set<string>(stored.autoWhitelist ?? [])
    const mergedWhitelist = new Set<string>([...storedWhitelist, ...DEFAULT_AUTO_WHITELIST])
    for (const t of storedRemoved) mergedWhitelist.delete(t)
    autoWhitelist.value = mergedWhitelist

    if (stored.alwaysAsk !== undefined) {
      alwaysAsk.value = new Set(stored.alwaysAsk)
    }
  }

  // Run hydrate immediately on store creation
  hydrate()

  // Watch all reactive state and persist on any change (deep: true for Set refs
  // doesn't help since we reassign, but deep covers nested objects if added later)
  watch(
    [policy, autoWhitelist, alwaysAsk, userRemovedTools, modelChoice],
    () => persist(),
    { deep: true },
  )

  // ─── Whitelist mutators (m2 reassign-Set pattern) ────────────────────────────

  function addToWhitelist(tool: string) {
    autoWhitelist.value = new Set([...autoWhitelist.value, tool])
    // If user is re-adding something they removed, clear the removal record
    const next = new Set(userRemovedTools.value)
    next.delete(tool)
    userRemovedTools.value = next
  }

  function removeFromWhitelist(tool: string) {
    const next = new Set(autoWhitelist.value)
    next.delete(tool)
    autoWhitelist.value = next
    // Track that user explicitly removed this default tool (m3)
    if (DEFAULT_AUTO_WHITELIST.has(tool)) {
      userRemovedTools.value = new Set([...userRemovedTools.value, tool])
    }
  }

  function addToAlwaysAsk(tool: string) {
    alwaysAsk.value = new Set([...alwaysAsk.value, tool])
  }

  function removeFromAlwaysAsk(tool: string) {
    const next = new Set(alwaysAsk.value)
    next.delete(tool)
    alwaysAsk.value = next
  }

  function setPolicy(p: AgentPolicy) {
    policy.value = p
  }

  function setModelChoice(m: string) {
    modelChoice.value = m
  }

  // ─── shouldConfirm helper ─────────────────────────────────────────────────

  /**
   * Determines whether a tool call needs explicit user confirmation.
   *
   * Decision matrix:
   *   policy === 'ask_all'  → always true
   *   policy === 'auto'     → false if in autoWhitelist, else true
   *   policy === 'custom'   → false if in autoWhitelist
   *                           true  if in alwaysAsk
   *                           false otherwise (neither list → auto-deny without prompt)
   *
   * Note: 'custom' panels with `execute` tool use panelSchema.execute.requiresConfirm
   * as an override when the tool name is 'execute'.
   */
  function shouldConfirm(toolCall: ToolCallLike, panelSchema?: PanelSchemaLike): boolean {
    const name = toolCall.name

    if (policy.value === 'ask_all') return true

    if (policy.value === 'auto') {
      return !autoWhitelist.value.has(name)
    }

    // policy === 'custom'
    if (autoWhitelist.value.has(name)) return false
    if (alwaysAsk.value.has(name)) return true

    // 'execute' tool: defer to panel schema if available
    if (name === 'execute' && panelSchema?.execute != null) {
      return panelSchema.execute.requiresConfirm
    }

    // Not in either list → auto-deny (no confirm prompt)
    return false
  }

  return {
    // state
    policy,
    autoWhitelist,
    alwaysAsk,
    userRemovedTools,
    modelChoice,
    // lifecycle
    hydrate,
    persist,
    // whitelist mutators
    addToWhitelist,
    removeFromWhitelist,
    addToAlwaysAsk,
    removeFromAlwaysAsk,
    // simple setters
    setPolicy,
    setModelChoice,
    // decision helper
    shouldConfirm,
  }
})
