/**
 * Agent Settings Store  (§6.7)
 *
 * 使用者偏好，持久化至 localStorage。
 *
 * policy（四模式；standard/full_auto/ask 為固定策略，不讀任何可編輯 set，
 *         只有 custom 才讀 autoWhitelist / alwaysAsk）：
 *   'standard'  — 只有「執行」類（EXECUTE_TOOLS）需確認，其餘自動（預設）
 *   'full_auto' — 全部自動，連「執行」都不確認
 *   'ask'       — 每次都問
 *   'custom'    — autoWhitelist 自動批准，alwaysAsk 彈窗，其餘 deny-by-default=ASK
 *
 * 舊值遷移（hydrate 時 migratePolicy）：'auto'→'standard'、'ask_all'→'ask'。
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

/** 預設自動批准的 7 個工具（§6.7 / §7 Tool inventory） */
export const DEFAULT_AUTO_WHITELIST: ReadonlySet<string> = new Set([
  'navigate_to',
  'select_subfunction',
  'load_file',
  'open_dropdown',
  'set_field',
  'list_files',
  'get_task_status',
])

/** 預設永遠詢問的 2 個工具（§6.7 / §7 Tool inventory；custom 模式的預設起點） */
export const DEFAULT_ALWAYS_ASK: ReadonlySet<string> = new Set([
  'click_execute',
  'click_action',
])

/**
 * 「執行」類動作 —— `standard` 模式據此判定是否需確認。
 * 與 useAgent.ts 執行閘（tc.function.name === 'click_execute' | 'click_action'）同名單。
 * 內容目前與 DEFAULT_ALWAYS_ASK 相同，但語意不同（前者是固定策略判準、
 * 後者是 custom 模式的可編輯預設），故獨立定義、不共用。
 */
export const EXECUTE_TOOLS: ReadonlySet<string> = new Set([
  'click_execute',
  'click_action',
])

export const AGENT_SETTINGS_KEY = 'agent_settings'

// ─── Types ────────────────────────────────────────────────────────────────────

export type AgentPolicy = 'standard' | 'full_auto' | 'ask' | 'custom'

/**
 * Policy 顯示/輪循順序 —— badge（點擊輪循）與設定頁 radio 共用的單一真實來源。
 * 順序即為 UI 呈現與 nextPolicy() 的環狀順序。
 */
export const POLICY_ORDER: readonly AgentPolicy[] = ['standard', 'full_auto', 'ask', 'custom']

/** 回傳輪循的下一個 policy；未知值（indexOf=-1）→ 'standard'。 */
export function nextPolicy(current: AgentPolicy): AgentPolicy {
  const i = POLICY_ORDER.indexOf(current)
  return POLICY_ORDER[(i + 1) % POLICY_ORDER.length]
}

// ─── Legacy policy migration ──────────────────────────────────────────────────

// 由 POLICY_ORDER 衍生，避免兩份清單漂移（Set 只用 .has()，順序無關）。
const VALID_POLICIES: ReadonlySet<string> = new Set<string>(POLICY_ORDER)

/** 舊 policy 值 → 新值（行為等價：auto=只問 execute=standard；ask_all=全問=ask） */
const LEGACY_POLICY_MAP: Record<string, AgentPolicy> = {
  auto: 'standard',
  ask_all: 'ask',
}

/** 把任意 stored policy 字串收斂成合法 AgentPolicy（未知值 fallback 'standard'） */
function migratePolicy(raw: string): AgentPolicy {
  if (VALID_POLICIES.has(raw)) return raw as AgentPolicy
  return LEGACY_POLICY_MAP[raw] ?? 'standard'
}

export interface ToolCallLike {
  name: string
  arguments?: Record<string, unknown>
}

export interface PanelSchemaLike {
  execute?: { requiresConfirm: boolean } | null
}

interface StoredSettings {
  policy?: string  // 放寬以容納舊值（auto/ask_all）；讀入時經 migratePolicy 收斂
  autoWhitelist?: string[]
  alwaysAsk?: string[]
  userRemovedTools?: string[]
  modelChoice?: string
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useAgentSettingsStore = defineStore('agentSettings', () => {
  const policy = ref<AgentPolicy>('standard')
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

    if (stored.policy) policy.value = migratePolicy(stored.policy)
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
   * Decision matrix (§8.1)：standard/full_auto/ask 為固定策略，不讀可編輯 set；
   * 只有 custom 才讀 autoWhitelist / alwaysAsk。
   *   policy === 'full_auto' → always false（全自動，連 execute 都不問）
   *   policy === 'ask'       → always true（每次都問）
   *   policy === 'standard'  → EXECUTE_TOOLS.has(name)（只有 execute 類要確認）
   *   policy === 'custom'    → alwaysAsk.has(name)      → true
   *                            autoWhitelist.has(name)  → false
   *                            click_execute + panelSchema.execute → requiresConfirm
   *                            otherwise                → true  (deny-by-default = ASK)
   */
  function shouldConfirm(toolCall: ToolCallLike, panelSchema?: PanelSchemaLike): boolean {
    const name = toolCall.name

    if (policy.value === 'full_auto') return false
    if (policy.value === 'ask') return true
    if (policy.value === 'standard') return EXECUTE_TOOLS.has(name)

    // policy === 'custom'
    if (alwaysAsk.value.has(name)) return true
    if (autoWhitelist.value.has(name)) return false

    // 'click_execute' tool: defer to panel schema if available
    if (name === 'click_execute' && panelSchema?.execute != null) {
      return panelSchema.execute.requiresConfirm
    }

    // Not in either list → deny-by-default = ASK (confirm required)
    return true
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
