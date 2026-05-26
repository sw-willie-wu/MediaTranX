/**
 * useAgentTools — 9 tool definitions + dispatcher.
 *
 * Spec §6.4 + §7.  Called by useAgent (default tools dep).
 *
 * Design notes:
 * - All store / router / registry access is done lazily inside each dispatcher
 *   function, NOT at module-level or composable-call time.  This makes the
 *   composable safe to call from any context (setup, outside setup, tests) and
 *   avoids "no active component instance" errors from useRouter / useRoute.
 * - Each dispatcher returns a ToolResult: { ok: true, ... } | { error: string, ... }
 * - dispatch() itself is a pure stateless function exported alongside the
 *   composable so tests can call it directly without Vue setup context.
 */

import { useRouter } from 'vue-router'
import { useActivePanel } from '@/composables/useActivePanel'
import { useActiveView } from '@/composables/useActiveView'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'

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
 * Lazily get the active panel entry.
 * Must be called inside a component setup context OR after installing pinia +
 * a router (for tests that use defineComponent + mount).
 */
function _getActivePanel() {
  const ap = useActivePanel()
  return ap.value
}

function _getActiveView() {
  const av = useActiveView()
  return av.value
}

// ─── Individual dispatchers ───────────────────────────────────────────────────

const dispatchers: Record<string, (args: any) => Promise<ToolResult>> = {

  navigate_to: async ({ route }: { route: string }): Promise<ToolResult> => {
    try {
      const router = useRouter()
      await router.push(route)
      return { ok: true }
    } catch (e: any) {
      return { error: 'agent.error.tool_failed', detail: String(e?.message ?? e) }
    }
  },

  select_subfunction: async ({ name }: { name: string }): Promise<ToolResult> => {
    try {
      const view = _getActiveView()
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
      const ap = _getActivePanel()
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
      const ap = _getActivePanel()
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
      const ap = _getActivePanel()
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
      const ap = _getActivePanel()
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

/**
 * Dispatch a tool call to the appropriate handler.
 * Must be called within a Vue component setup context (for router/stores).
 */
export function dispatch(tc: ToolCall): Promise<ToolResult> {
  const fn = dispatchers[tc.function.name]
  if (!fn) {
    return Promise.resolve({ error: 'agent.error.unknown_tool', tool: tc.function.name })
  }

  let args: any
  try {
    args = JSON.parse(tc.function.arguments)
  } catch (e: any) {
    return Promise.resolve({ error: 'agent.error.tool_failed', detail: 'arguments not valid JSON' })
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
