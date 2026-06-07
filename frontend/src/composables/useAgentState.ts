/**
 * useAgentState — builds the two-tier UI "state snapshot" injected into the
 * agent each round (spec 2026-06-07). Pure function: takes already-resolved
 * inputs (no vue-router / setup context), so it unit-tests in node-env and the
 * runLoop can call it without a component instance.
 *
 * Field metadata in PanelFieldSchema is lazy getters (options/min/max/visibleWhen);
 * this is where they get materialized into plain JSON scalars.
 */
import { AGENT_NAV_CATALOG } from '@/agent/agentNavCatalog'
import type { PanelAgentSchema } from '@/stores/panelRegistry'

export interface SnapshotFileRef { id: string; name: string; kind: string }

export interface SnapshotField {
  name: string
  type: string
  current_value: unknown
  options?: string[]
  min?: number
  max?: number
  step?: number
  visible: boolean
}

export interface AgentStateSnapshot {
  map: {
    views: { route: string; label: string; subfunctions: string[] }[]
    files: SnapshotFileRef[]
    current_position: { view: string | null; subfunction: string | null }
  }
  active_panel: {
    panel_id: string
    fields: SnapshotField[]
    actions: { name: string; label?: string }[]
    execute: { requires_confirm: boolean; label?: string } | null
  } | null
  active_file: SnapshotFileRef | null
}

export interface SnapshotInputs {
  activePanel: {
    panelId: string
    schema: PanelAgentSchema
    currentValues: Record<string, unknown>
  } | null
  currentRoute: string | null
  currentSubfunction: string | null
  files: SnapshotFileRef[]
  activeFile: SnapshotFileRef | null
}

/** Resolve a `number | (() => number)` union to a number (or undefined). */
function resolveNum(v: number | (() => number) | undefined): number | undefined {
  if (typeof v === 'function') return v()
  return v
}

export function buildAgentStateSnapshot(inp: SnapshotInputs): AgentStateSnapshot {
  const views = AGENT_NAV_CATALOG.map(e => ({
    route: e.route,
    label: e.label,
    subfunctions: e.subfunctions,
  }))

  let active_panel: AgentStateSnapshot['active_panel'] = null
  if (inp.activePanel) {
    const { panelId, schema, currentValues } = inp.activePanel
    active_panel = {
      panel_id: panelId,
      fields: schema.fields.map(f => {
        const field: SnapshotField = {
          name: f.name,
          type: f.type,
          current_value: currentValues[f.name] ?? null,
          visible: f.visibleWhen ? f.visibleWhen() : true,
        }
        if (f.options) field.options = f.options()
        const mn = resolveNum(f.min)
        const mx = resolveNum(f.max)
        if (mn !== undefined) field.min = mn
        if (mx !== undefined) field.max = mx
        if (f.step !== undefined) field.step = f.step
        return field
      }),
      actions: schema.actions.map(a => ({ name: a.name, label: a.label })),
      execute: schema.execute
        ? { requires_confirm: schema.execute.requiresConfirm, label: schema.execute.label }
        : null,
    }
  }

  return {
    map: {
      views,
      files: inp.files,
      current_position: { view: inp.currentRoute, subfunction: inp.currentSubfunction },
    },
    active_panel,
    active_file: inp.activeFile,
  }
}
