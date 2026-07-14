/**
 * Panel Registry  (§6.5)
 *
 * Plain module-level Map (NOT Pinia) keyed by panelId.
 * Tool panels register themselves in onMounted / onUnmounted via
 * useAgentPanelHost composable.
 * Agent tools call panelRegistry.get(panelId) to read/mutate panel state.
 */
import type { Ref } from 'vue'

// ─── Schema types ─────────────────────────────────────────────────────────────

export interface PanelFieldSchema {
  name: string
  type: 'enum' | 'number' | 'bool' | 'string'
  options?: () => string[]
  min?: number | (() => number)
  max?: number | (() => number)
  step?: number
  visibleWhen?: () => boolean
  /** 給 LLM 的欄位語意說明（選配；由 META.agentHint 餵入） */
  description?: string
}

export interface PanelActionSchema {
  name: string
  label?: string
}

/**
 * The schema a panel exposes to the agent.
 * `execute` is null for settings-only panels (no submit button).
 */
export interface PanelAgentSchema {
  panelId: string
  fields: PanelFieldSchema[]
  actions: PanelActionSchema[]
  execute: { requiresConfirm: boolean; label?: string } | null
}

// ─── Handle type ──────────────────────────────────────────────────────────────

export interface PanelHandle {
  agentSchema: PanelAgentSchema
  /** Return current values of all fields as a plain object */
  getCurrentValues: () => Record<string, unknown>
  /** Set a field to a value; returns the clamped / coerced actual value */
  setField: (field: string, value: unknown) => unknown
  /** Programmatically open/focus a field (e.g. open a dropdown) */
  openField: (field: string) => void
  /** Trigger the panel's primary submit action */
  execute: () => Promise<{ task_id?: string }> | { task_id?: string }
  /** Trigger a named action button (optional — not all panels have extra actions) */
  invokeAction?: (name: string) => unknown
  /** True if the panel supports multi-select mode */
  isMultiSelect: () => boolean
  /** Reactive flag: true while the panel component is mounted in the DOM */
  isMounted: Ref<boolean>
}

// ─── Registry ─────────────────────────────────────────────────────────────────

const _registry = new Map<string, PanelHandle>()

export const panelRegistry = {
  register(panelId: string, handle: PanelHandle): void {
    _registry.set(panelId, handle)
  },

  unregister(panelId: string): void {
    _registry.delete(panelId)
  },

  get(panelId: string): PanelHandle | undefined {
    return _registry.get(panelId)
  },

  /** For tests — clear all entries between test cases */
  _clearAll(): void {
    _registry.clear()
  },
}
