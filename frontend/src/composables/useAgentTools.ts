/**
 * useAgentTools — 9 tool definitions + dispatcher.
 *
 * Spec §6.4 + §7.  Called by useAgent (default tools dep).
 *
 * Design notes:
 * - All store / router / registry access is done lazily inside each dispatcher
 *   function (NOT at module-level or composable-call time).  This keeps the
 *   composable safe to call from any context — setup, outside setup, vitest
 *   node env — and avoids "no active component instance" errors from
 *   useRouter / useRoute.
 * - `useRouter()` itself uses `inject()` and therefore needs an active setup
 *   context, so the router is reached via dynamic `import('@/router')` from
 *   inside each dispatcher.  The module is loaded once at app boot, so the
 *   dynamic import is essentially free at call time.  This also stops the
 *   `createWebHashHistory()` side-effect from firing at module-load time in
 *   node-env tests that don't need the router at all.
 * - Each dispatcher returns a ToolResult: { ok: true, ... } | { error: string, ... }
 * - dispatch() itself is a pure stateless function exported alongside the
 *   composable so tests can call it directly without Vue setup context.
 */

import { getCurrentInstance } from 'vue'
import { useRouter, type Router } from 'vue-router'
import { useActivePanel } from '@/composables/useActivePanel'
import { useActiveView, deriveViewId } from '@/composables/useActiveView'
import { viewRegistry } from '@/stores/viewRegistry'
import { panelRegistry } from '@/stores/panelRegistry'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useAgentStore } from '@/stores/agent'

/**
 * Resolve a Router instance.
 *
 * When called from inside an active Vue setup() (e.g. the test harness which
 * mounts a component with a memory-history router as a plugin), prefer
 * `useRouter()` so test-injected routers and their spies are honoured.
 *
 * When called outside setup (the production path: dispatchers run from the
 * useAgent runLoop, which is plain async code) `useRouter()` would log a
 * "inject() can only be used inside setup()" warning AND return `undefined`,
 * so we fall back to a dynamic import of the global singleton.  The dynamic
 * import keeps `createWebHashHistory()` off the module-load path of files
 * that only need the dispatchers (e.g. node-env tests that don't navigate).
 */
async function resolveRouter(): Promise<Router> {
  if (getCurrentInstance() !== null) {
    const r = useRouter()
    if (r) return r
  }
  const mod = await import('@/router')
  return mod.default
}

// ─── Public types ─────────────────────────────────────────────────────────────

export interface ToolDefinition {
  name: string
  description: string
  parameters: object
}

export type ToolResult =
  | { ok: true; [k: string]: any }
  | { error: string; [k: string]: any }

export interface ToolCall {
  id: string
  type: 'function'
  function: { name: string; arguments: string }
}

// ─── Tool definitions (§7) ───────────────────────────────────────────────────

export const TOOLS: ToolDefinition[] = [
  {
    name: 'navigate_to',
    description: 'Navigate to a top-level domain view (image/audio/video/document/settings/tasks/home).',
    parameters: {
      type: 'object',
      properties: {
        route: {
          type: 'string',
          enum: ['/', '/image', '/audio', '/video', '/document', '/settings', '/tasks'],
        },
      },
      required: ['route'],
    },
  },
  {
    name: 'select_subfunction',
    description:
      'Select a sub-function within the current view (e.g. "upscale", "transcode"). For settings, also selects tab.',
    parameters: {
      type: 'object',
      properties: { name: { type: 'string' } },
      required: ['name'],
    },
  },
  {
    name: 'load_file',
    description: 'Set the active file by file_id. Use list_files first to discover ids.',
    parameters: {
      type: 'object',
      properties: { file_id: { type: 'string' } },
      required: ['file_id'],
    },
  },
  {
    name: 'list_files',
    description: 'List currently uploaded files. Returns array of {id, name, kind, size_bytes}.',
    parameters: { type: 'object', properties: {} },
  },
  {
    name: 'open_dropdown',
    description: 'Open a dropdown field on the active panel (educational/optional, for visibility).',
    parameters: {
      type: 'object',
      properties: { field: { type: 'string' } },
      required: ['field'],
    },
  },
  {
    name: 'set_field',
    description: 'Set a field on the active panel. Field name & valid values are in state.panel_schema.',
    parameters: {
      type: 'object',
      properties: {
        field: { type: 'string' },
        value: {},
      },
      required: ['field', 'value'],
    },
  },
  {
    name: 'click_execute',
    description: "Submit the active panel's task with the currently set fields.",
    parameters: { type: 'object', properties: {} },
  },
  {
    name: 'click_action',
    description:
      'Invoke a named action button on the active panel/settings (browse, download, restart, delete...).',
    parameters: {
      type: 'object',
      properties: { name: { type: 'string' } },
      required: ['name'],
    },
  },
  {
    name: 'get_task_status',
    description: 'Get current status of a submitted task by id.',
    parameters: {
      type: 'object',
      properties: { task_id: { type: 'string' } },
      required: ['task_id'],
    },
  },
]

// ─── Dispatcher helpers ───────────────────────────────────────────────────────

/**
 * Lazily get the active view / panel entry.
 *
 * In a setup context (the vitest harness mounts dispatchers inside a
 * defineComponent with router + pinia plugins), the composable form works
 * and resolves the inject-based useRoute() correctly.
 *
 * From the runLoop async path (production), there is no setup context, so
 * useRoute() returns undefined and `route.path` crashes with "Cannot read
 * properties of undefined (reading 'path')". Fall back to deriving the path
 * from the router singleton's `currentRoute` and looking up the registry
 * directly — exactly what the composable does, just without inject().
 */
async function _getActiveView() {
  if (getCurrentInstance() !== null) {
    const av = useActiveView()
    return av.value
  }
  const router = await resolveRouter()
  const path = router.currentRoute.value.path
  const viewId = deriveViewId(path)
  if (!viewId) return null
  return viewRegistry.get(viewId) ?? null
}

async function _getActivePanel() {
  if (getCurrentInstance() !== null) {
    const ap = useActivePanel()
    return ap.value
  }
  const router = await resolveRouter()
  const path = router.currentRoute.value.path
  const viewId = deriveViewId(path)
  if (!viewId) return null
  const view = viewRegistry.get(viewId)
  if (!view) return null
  const fn = view.currentFunction.value
  if (!fn) return null
  const panelId = `${viewId}.${fn}`
  const entry = panelRegistry.get(panelId)
  if (!entry) return null
  return {
    panelId,
    schema: entry.agentSchema,
    instance: entry,
    isMounted: entry.isMounted.value,
  }
}

// ─── Individual dispatchers ───────────────────────────────────────────────────

const dispatchers: Record<string, (args: any) => Promise<ToolResult>> = {

  navigate_to: async ({ route }: { route: string }): Promise<ToolResult> => {
    try {
      useAgentStore().setCurrentAction('agent.banner.act.navigate_to', { route })
      const router = await resolveRouter()
      await router.push(route)
      return { ok: true }
    } catch (e: any) {
      return { error: 'agent.error.tool_failed', detail: String(e?.message ?? e) }
    }
  },

  select_subfunction: async ({ name }: { name: string }): Promise<ToolResult> => {
    try {
      useAgentStore().setCurrentAction('agent.banner.act.select_subfunction', { name })
      const view = await _getActiveView()
      if (!view || !view.setCurrentFunction) {
        return { error: 'agent.error.view_not_introspectable' }
      }
      view.setCurrentFunction(name)
      return { ok: true }
    } catch (e: any) {
      return { error: 'agent.error.tool_failed', detail: String(e?.message ?? e) }
    }
  },

  load_file: async ({ file_id }: { file_id: string }): Promise<ToolResult> => {
    try {
      useAgentStore().setCurrentAction('agent.banner.act.load_file', { file_id })
      const filesStore = useFilesStore()
      // setCurrentFile is the available API in the store
      if (typeof filesStore.setCurrentFile !== 'function') {
        return { error: 'agent.error.tool_failed', detail: 'filesStore.setCurrentFile not available' }
      }
      // Check file exists first
      const file = filesStore.files.get(file_id)
      if (!file) {
        // Try fetching info from backend
        const fetched = await filesStore.getFileInfo(file_id)
        if (!fetched) return { error: 'agent.error.file_not_found', file_id }
      }
      filesStore.setCurrentFile(file_id)
      return { ok: true }
    } catch (e: any) {
      return { error: 'agent.error.tool_failed', detail: String(e?.message ?? e) }
    }
  },

  list_files: async (): Promise<ToolResult> => {
    try {
      useAgentStore().setCurrentAction('agent.banner.act.list_files', {})
      const filesStore = useFilesStore()
      const files = filesStore.allFiles.map(f => ({
        id: f.id,
        name: f.originalName ?? f.name,
        kind: f.type,
        size_bytes: f.size,
      }))
      return { ok: true, files }
    } catch (e: any) {
      return { error: 'agent.error.tool_failed', detail: String(e?.message ?? e) }
    }
  },

  open_dropdown: async ({ field }: { field: string }): Promise<ToolResult> => {
    try {
      useAgentStore().setCurrentAction('agent.banner.act.open_dropdown', { field })
      const ap = await _getActivePanel()
      if (!ap) return { error: 'agent.error.panel_not_active' }
      if (!ap.isMounted) return { error: 'agent.error.panel_not_active' }
      ap.instance.openField(field)
      return { ok: true }
    } catch (e: any) {
      return { error: 'agent.error.tool_failed', detail: String(e?.message ?? e) }
    }
  },

  set_field: async ({ field, value }: { field: string; value: unknown }): Promise<ToolResult> => {
    try {
      const displayValue = value !== null && typeof value === 'object' ? JSON.stringify(value) : String(value)
      useAgentStore().setCurrentAction('agent.banner.act.set_field', { field, value: displayValue })
      const ap = await _getActivePanel()
      if (!ap) return { error: 'agent.error.panel_not_supported' }
      if (!ap.isMounted) return { error: 'agent.error.panel_not_active' }

      const fieldDef = ap.schema.fields.find(f => f.name === field)
      if (!fieldDef) {
        return {
          error: 'agent.error.invalid_field',
          field,
          allowed: ap.schema.fields.map(f => f.name),
        }
      }

      // Enum validation with case-insensitive matching (OQ-6)
      let coercedValue = value
      if (fieldDef.type === 'enum' && fieldDef.options) {
        const opts = fieldDef.options()
        const matched = opts.find(o => o.toLowerCase() === String(value).toLowerCase())
        if (!matched) {
          return {
            error: 'agent.error.invalid_field',
            field,
            allowed: opts,
          }
        }
        coercedValue = matched
      }

      const actual = ap.instance.setField(field, coercedValue)
      return { ok: true, requested: value, actual }
    } catch (e: any) {
      return { error: 'agent.error.tool_failed', detail: String(e?.message ?? e) }
    }
  },

  click_execute: async (): Promise<ToolResult> => {
    try {
      useAgentStore().setCurrentAction('agent.banner.act.click_execute', {})
      const ap = await _getActivePanel()
      if (!ap) return { error: 'agent.error.panel_not_supported' }
      if (!ap.isMounted) return { error: 'agent.error.panel_not_active' }

      // Settings panels have execute: null (§6.5c)
      if (ap.schema.execute === null) {
        return { error: 'agent.error.no_execute_on_settings' }
      }

      if (ap.instance.isMultiSelect()) {
        return { error: 'agent.error.multi_select_not_supported' }
      }

      const result = await ap.instance.execute()
      return { ok: true, task_id: result?.task_id }
    } catch (e: any) {
      // Catch the sentinel thrown by settings panels' execute()
      if (String(e?.message ?? e).includes('agent.error.no_execute_on_settings')) {
        return { error: 'agent.error.no_execute_on_settings' }
      }
      return { error: 'agent.error.tool_failed', detail: String(e?.message ?? e) }
    }
  },

  click_action: async ({ name }: { name: string }): Promise<ToolResult> => {
    try {
      useAgentStore().setCurrentAction('agent.banner.act.click_action', { name })
      const ap = await _getActivePanel()
      if (!ap) return { error: 'agent.error.panel_not_supported' }
      if (!ap.isMounted) return { error: 'agent.error.panel_not_active' }

      // Validate name against schema.actions
      const actionDef = ap.schema.actions.find(a => a.name === name)
      if (!actionDef) {
        return {
          error: 'agent.error.invalid_action',
          name,
          allowed: ap.schema.actions.map(a => a.name),
        }
      }

      if (!ap.instance.invokeAction) {
        return { error: 'agent.error.invalid_action', name }
      }

      const result = await ap.instance.invokeAction(name)
      return { ok: true, result }
    } catch (e: any) {
      return { error: 'agent.error.tool_failed', detail: String(e?.message ?? e) }
    }
  },

  get_task_status: async ({ task_id }: { task_id: string }): Promise<ToolResult> => {
    try {
      useAgentStore().setCurrentAction('agent.banner.act.get_task_status', { task_id })
      const tasksStore = useTaskStore()
      const task = tasksStore.tasks.get(task_id)
      if (!task) {
        return { error: 'agent.error.tool_failed', detail: `task ${task_id} not found` }
      }
      return {
        ok: true,
        status: {
          task_id: task.taskId,
          task_type: task.taskType,
          status: task.status,
          progress: task.progress,
          message: task.message,
          result: task.result,
          error: task.error,
        },
      }
    } catch (e: any) {
      return { error: 'agent.error.tool_failed', detail: String(e?.message ?? e) }
    }
  },
}

// ─── Public dispatch function ─────────────────────────────────────────────────

// Required-field schema derived from TOOLS so dispatch() can short-circuit
// when a model emits a tool call with missing arguments (bug #15 model-quality
// case observed live with qwen3:8b emitting navigate_to({}) — would otherwise
// fall through to router.push(undefined) and a cryptic vue-router error).
const REQUIRED_BY_TOOL: Record<string, readonly string[]> = Object.fromEntries(
  TOOLS.map(t => [
    t.name,
    Array.isArray((t.parameters as any)?.required)
      ? ((t.parameters as any).required as string[])
      : [],
  ]),
)

/**
 * Dispatch a tool call to the appropriate handler.  Safe to call from any
 * execution context; all store / router access inside the dispatchers is
 * lazy (see header note).
 */
export function dispatch(tc: ToolCall): Promise<ToolResult> {
  const fn = dispatchers[tc.function.name]
  if (!fn) {
    return Promise.resolve({ error: 'agent.error.unknown_tool', tool: tc.function.name })
  }

  // Defense-in-depth: empty / whitespace `arguments` is treated as "{}"
  // (the SSE assembler already normalizes the wire path; this covers
  // direct callers / tests that bypass the assembler).
  let args: any
  const raw = (tc.function.arguments ?? '').trim()
  if (!raw) {
    args = {}
  } else {
    try {
      args = JSON.parse(raw)
    } catch (e: any) {
      return Promise.resolve({ error: 'agent.error.tool_failed', detail: 'arguments not valid JSON' })
    }
  }

  // Surface missing-required errors back to the model with a clear typed code
  // (agent.error.invalid_field) instead of dispatching and crashing the
  // dispatcher with whatever the dependency throws on an undefined.
  const required = REQUIRED_BY_TOOL[tc.function.name] ?? []
  for (const field of required) {
    if (args == null || args[field] === undefined || args[field] === '') {
      return Promise.resolve({
        error: 'agent.error.invalid_field',
        field,
        detail: `tool ${tc.function.name} requires field "${field}"`,
      })
    }
  }

  return fn(args).catch((e: any) => ({
    error: 'agent.error.tool_failed',
    detail: String(e?.message ?? e),
  }))
}

// ─── Composable ───────────────────────────────────────────────────────────────

export function useAgentTools() {
  return { TOOLS, dispatch }
}
