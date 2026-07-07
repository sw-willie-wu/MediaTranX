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
import { useActiveView, deriveViewId, panelIdFor } from '@/composables/useActiveView'
import { viewRegistry, type ViewHandle } from '@/stores/viewRegistry'
import { panelRegistry, type PanelAgentSchema } from '@/stores/panelRegistry'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useAgentStore } from '@/stores/agent'

// ─── Bug #21: nested value unwrap helper ─────────────────────────────────────

/**
 * Bug #21: local models (qwen3:8b, qwen3.5:9b without strict-mode equivalent) often
 * wrap set_field's `value` arg in a nested object: `{field: 'grayscale', value: {value: 50}}`
 * or `{field: 'mode', value: {mode: 'anime'}}`. Detect this single-key-wrapping pattern
 * (key === field name OR key === 'value') and extract the inner scalar.
 *
 * Does NOT unwrap when value has multiple keys, or when the single key doesn't match —
 * those are real object values (rare, but reserved for future panels with object fields).
 */
export function _unwrapNestedValue(field: string, value: unknown): unknown {
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    const keys = Object.keys(value as Record<string, unknown>)
    if (keys.length === 1 && (keys[0] === field || keys[0] === 'value')) {
      return (value as Record<string, unknown>)[keys[0]]
    }
  }
  return value
}

/**
 * Bug #23: qwen3.5 (and some other non-strict-mode local models) occasionally
 * JSON-quote their string enum arguments, emitting
 *   "value": "\"jpg\""
 * on the wire instead of the expected
 *   "value": "jpg"
 * JSON.parse on the tool-call arguments turns that into the literal 5-char
 * string `"jpg"` (quote chars included), which then fails the enum match.
 *
 * Strip exactly one layer of JSON-quote-wrap when the value is a string of
 * the form `"..."` AND parses cleanly to another string. Single-pass — we
 * trust the model to overquote at most once.
 */
export function _stripJsonStringWrap(value: unknown): unknown {
  if (typeof value !== 'string' || value.length < 2) return value
  if (!value.startsWith('"') || !value.endsWith('"')) return value
  try {
    const parsed = JSON.parse(value)
    return typeof parsed === 'string' ? parsed : value
  } catch {
    return value
  }
}

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

/** Extract a human-readable message from an unknown caught value. */
function errMsg(e: unknown): string {
  return String(e instanceof Error ? e.message : e)
}

// ─── Public types ─────────────────────────────────────────────────────────────

export interface ToolDefinition {
  name: string
  description: string
  parameters: object
}

export type ToolResult =
  | { ok: true; [k: string]: unknown }
  | { error: string; [k: string]: unknown }

export interface ToolCall {
  id: string
  type: 'function'
  function: { name: string; arguments: string }
}

// ─── Tool definitions (§7) ───────────────────────────────────────────────────

// 8 non-set_field tools (static). set_field is generated dynamically in getTools().
const _NON_SET_FIELD_TOOLS: ToolDefinition[] = [
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
  // set_field is at index 5 in the final array — generated dynamically in getTools()
  {
    name: 'click_execute',
    description:
      "Submit the active panel's task. ONLY call when the user gives an explicit " +
      'execute/run/apply/start command. MUST NOT call for mere setup/adjust ' +
      '("set...", "change...", "switch to..."); after setting fields, stop and ' +
      'report. If unsure whether to submit, ask the user first.',
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
    description: 'Get current status of a submitted task by id, or of a pipeline run by run_id.',
    parameters: {
      type: 'object',
      properties: { task_id: { type: 'string' }, run_id: { type: 'string' } },
    },
  },
  {
    name: 'create_pipeline',
    description:
      'Draft a multi-step pipeline on the Pipeline canvas from a complete graph. ' +
      'nodes: [{id, kind: "input"|"source"|"tool", tool_key?, params?}] — exactly one root ' +
      '(kind "input" for user files, or "source" with tool_key "video.download" + params.url). ' +
      'Tool nodes need tool_key like "video.transcode", "image.compress". ' +
      'edges: [{from, to}] connect node ids (no merging; one input per tool node). ' +
      'This only DRAFTS the graph for the user to review — it does NOT run. ' +
      'Call run_pipeline afterwards ONLY on explicit user command.',
    parameters: {
      type: 'object',
      properties: {
        name: { type: 'string' },
        nodes: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              id: { type: 'string' },
              kind: { type: 'string', enum: ['input', 'source', 'tool'] },
              tool_key: { type: 'string' },
              params: { type: 'object' },
            },
            required: ['id', 'kind'],
          },
        },
        edges: {
          type: 'array',
          items: {
            type: 'object',
            properties: { from: { type: 'string' }, to: { type: 'string' } },
            required: ['from', 'to'],
          },
        },
      },
      required: ['nodes', 'edges'],
    },
  },
  {
    name: 'run_pipeline',
    description:
      'Run the pipeline currently drafted on the canvas. input_file_ids is required when the ' +
      'root is an "input" node (use list_files to discover ids); omit for a "source" root. ' +
      'ONLY call on an explicit user execute/run command — same rule as click_execute.',
    parameters: {
      type: 'object',
      properties: {
        input_file_ids: { type: 'array', items: { type: 'string' } },
      },
    },
  },
]

/**
 * Build the 9-tool array with dynamic set_field and select_subfunction definitions.
 *
 * When activePanelSchema is provided and has fields, set_field.field becomes
 * an enum of panel field names — enabling OpenAI strict-mode constrained
 * decoding and Gemini/Ollama schema-respecting models to self-correct (§5.3.1,
 * Appendix D).
 *
 * Bug #22: When activeViewHandle is provided and declares validSubfunctions(),
 * select_subfunction.parameters.name becomes a dynamic enum of the valid IDs,
 * preventing the model from guessing wrong subfunction names (e.g. "transcode"
 * for Image domain when it was "convert").
 *
 * Order: navigate, select, load, list, open_dropdown, set_field, click_exec,
 *        click_action, get_status.
 */
export function getTools(
  activePanelSchema?: PanelAgentSchema | null,
  activeViewHandle?: ViewHandle | null,
): ToolDefinition[] {
  // Bug #22: dynamic enum for select_subfunction.name
  const subfnEnum = activeViewHandle?.validSubfunctions?.() ?? []
  const selectSubfunctionDef: ToolDefinition = {
    name: 'select_subfunction',
    description:
      'Select a sub-function within the current view (e.g. "upscale", "transcode"). For settings, also selects tab.',
    parameters: {
      type: 'object',
      properties: {
        name: subfnEnum.length > 0
          ? { type: 'string', enum: subfnEnum }
          : { type: 'string' },
      },
      required: ['name'],
    },
  }

  const setFieldDef: ToolDefinition = {
    name: 'set_field',
    description:
      'Set a field on the active panel. Use ONLY field names listed in the ' +
      'active_panel.fields of the current state; pick values from each field\'s ' +
      'options. Do not invent fields or guess values.',
    parameters: {
      type: 'object',
      properties: {
        field: activePanelSchema && activePanelSchema.fields.length > 0
          ? { type: 'string', enum: activePanelSchema.fields.map(f => f.name) }
          : { type: 'string' },
        // Bug #21: empty schema let local models emit nested {value: x} or {[field]: x}.
        // anyOf restricts to scalar types — guides schema-respecting models to scalar.
        // Shape matches backend _STRICT_PRIMITIVE_ANYOF exactly so _strictify_schema
        // passes through via idempotency check (OpenAI strict mode compatible).
        // Dispatcher _unwrapNestedValue below is the safety net for non-strict providers.
        value: {
          anyOf: [
            { type: 'string' },
            { type: 'number' },
            { type: 'boolean' },
            { type: 'null' },
          ],
        },
      },
      required: ['field', 'value'],
    },
  }

  // Build tool list: replace the static select_subfunction + set_field placeholders
  // with their dynamic equivalents.
  // Original _NON_SET_FIELD_TOOLS order: [navigate, select_subfunction, load, list, open_dropdown, click_exec, click_action, get_status]
  // Index 0=navigate, 1=select_subfunction, 2=load, 3=list, 4=open_dropdown, 5=click_exec, 6=click_action, 7=get_status
  return [
    _NON_SET_FIELD_TOOLS[0],  // navigate_to
    selectSubfunctionDef,     // dynamic select_subfunction (Bug #22)
    _NON_SET_FIELD_TOOLS[2],  // load_file
    _NON_SET_FIELD_TOOLS[3],  // list_files
    _NON_SET_FIELD_TOOLS[4],  // open_dropdown
    setFieldDef,              // dynamic set_field
    ..._NON_SET_FIELD_TOOLS.slice(5), // click_execute, click_action, get_task_status
  ]
}

// Backward-compat: callers using the static TOOLS array continue to work
export const TOOLS: ToolDefinition[] = getTools(null)

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
  const panelId = panelIdFor(viewId, fn)
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

// Canonical top-level routes navigate_to can reach. Single source of truth for
// the word<->path mapping. The model may pass a bare word ("settings") or a path
// ("/settings"); both resolve here. CRITICAL: home is "/", NOT "/home" — the tool
// description advertises "home", so it MUST map to "/" or it lands on a dead route.
const NAV_ROUTES: Record<string, string> = {
  home: '/',
  image: '/image',
  audio: '/audio',
  video: '/video',
  document: '/document',
  tasks: '/tasks',
  settings: '/settings',
}

/**
 * Resolve the model's `route` arg to a canonical path. Known words map to their
 * path; empty / "/" is home; anything else is treated as a literal path (then
 * validated against the router before navigating, in navigate_to).
 */
function resolveNavRoute(input: string): string {
  const word = (input ?? '').trim().toLowerCase().replace(/^\/+/, '')
  if (word === '') return '/'
  return NAV_ROUTES[word] ?? '/' + word
}

/**
 * Per-dispatch context. Carries the run's AbortSignal so a state-mutating tool
 * that is already in flight when the user presses stop can refuse to apply its
 * change (checked right before the mutation). Optional so existing/direct
 * callers and read-only tools are unaffected.
 *
 * The check is a point-check right before the mutation, so it fully closes the
 * race for synchronous mutations (set_field — the reported bug). For tools whose
 * mutation is itself awaited (navigate_to/click_execute/click_action), an abort
 * arriving mid-await is best-effort — cooperative cancellation inside those
 * calls would be needed to interrupt them, which is out of scope here.
 */
export type DispatchCtx = { signal?: AbortSignal }

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const dispatchers: Record<string, (args: any, ctx: DispatchCtx) => Promise<ToolResult>> = {

  navigate_to: async ({ route }: { route: string }, ctx: DispatchCtx): Promise<ToolResult> => {
    try {
      const path = resolveNavRoute(route)
      const router = await resolveRouter()
      // Validate BEFORE navigating. Vue Router's push() does NOT throw for an
      // unmatched path — it silently navigates to a dead (0-component) location
      // and resolves — so guarding on push alone would both move the app to a
      // blank view AND falsely report ok:true. router.resolve() reports the
      // matched route records without moving the app, so a bad route never
      // navigates and is reported back so the model can self-correct.
      if (router.resolve(path).matched.length === 0) {
        return { error: 'agent.error.invalid_route', route, allowed: Object.keys(NAV_ROUTES) }
      }
      useAgentStore().setCurrentAction('agent.banner.act.navigate_to', { route })
      if (ctx.signal?.aborted) return { error: 'agent.error.aborted' }
      await router.push(path)
      return { ok: true }
    } catch (e: unknown) {
      return { error: 'agent.error.tool_failed', detail: errMsg(e) }
    }
  },

  select_subfunction: async ({ name }: { name: string }, ctx: DispatchCtx): Promise<ToolResult> => {
    try {
      useAgentStore().setCurrentAction('agent.banner.act.select_subfunction', { name })
      const view = await _getActiveView()
      if (!view || !view.setCurrentFunction) {
        return { error: 'agent.error.view_not_introspectable' }
      }
      // Bug #22: validate name against view's declared valid subfunction list.
      // Views without validSubfunctions (backward compat) pass through unchecked.
      const allowed = view.validSubfunctions?.() ?? []
      if (allowed.length > 0 && !allowed.includes(name)) {
        return { error: 'agent.error.invalid_subfunction', name, allowed }
      }
      if (ctx.signal?.aborted) return { error: 'agent.error.aborted' }
      view.setCurrentFunction(name)
      return { ok: true }
    } catch (e: unknown) {
      return { error: 'agent.error.tool_failed', detail: errMsg(e) }
    }
  },

  load_file: async ({ file_id }: { file_id: string }, ctx: DispatchCtx): Promise<ToolResult> => {
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
      if (ctx.signal?.aborted) return { error: 'agent.error.aborted' }
      filesStore.setCurrentFile(file_id)
      return { ok: true }
    } catch (e: unknown) {
      return { error: 'agent.error.tool_failed', detail: errMsg(e) }
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
    } catch (e: unknown) {
      return { error: 'agent.error.tool_failed', detail: errMsg(e) }
    }
  },

  open_dropdown: async ({ field }: { field: string }, ctx: DispatchCtx): Promise<ToolResult> => {
    try {
      useAgentStore().setCurrentAction('agent.banner.act.open_dropdown', { field })
      const ap = await _getActivePanel()
      if (!ap) return { error: 'agent.error.panel_not_active' }
      if (!ap.isMounted) return { error: 'agent.error.panel_not_active' }
      if (ctx.signal?.aborted) return { error: 'agent.error.aborted' }
      ap.instance.openField(field)
      return { ok: true }
    } catch (e: unknown) {
      return { error: 'agent.error.tool_failed', detail: errMsg(e) }
    }
  },

  set_field: async ({ field, value }: { field: string; value: unknown }, ctx: DispatchCtx): Promise<ToolResult> => {
    try {
      // Bug #21: unwrap single-key nested object emitted by local models without strict mode.
      // e.g. {value: {value: 50}} → {value: 50}  or  {value: {mode: 'anime'}} → {value: 'anime'}
      // Bug #23: strip one layer of JSON-quote-wrap from string values
      // (qwen3.5 sometimes emits `"\"jpg\""` instead of `"jpg"`).
      const unwrappedValue = _stripJsonStringWrap(_unwrapNestedValue(field, value))
      const displayValue = unwrappedValue !== null && typeof unwrappedValue === 'object' ? JSON.stringify(unwrappedValue) : String(unwrappedValue)
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
      let coercedValue = unwrappedValue
      if (fieldDef.type === 'enum' && fieldDef.options) {
        const opts = fieldDef.options()
        const matched = opts.find(o => o.toLowerCase() === String(unwrappedValue).toLowerCase())
        if (!matched) {
          return {
            error: 'agent.error.invalid_field',
            field,
            allowed: opts,
          }
        }
        coercedValue = matched
      }

      if (ctx.signal?.aborted) return { error: 'agent.error.aborted' }
      const actual = ap.instance.setField(field, coercedValue)
      return { ok: true, requested: value, actual }
    } catch (e: unknown) {
      return { error: 'agent.error.tool_failed', detail: errMsg(e) }
    }
  },

  click_execute: async (_args: unknown, ctx: DispatchCtx): Promise<ToolResult> => {
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

      // Universal gate: every tool panel (image/audio/video/document)
      // requires an active file. Without one the UI's Apply button is
      // disabled; the dispatcher must refuse for the same reason so the
      // agent doesn't fire a phantom submit + report success.
      if (useFilesStore().currentFile == null) {
        return { error: 'agent.error.no_file_selected' }
      }

      if (ctx.signal?.aborted) return { error: 'agent.error.aborted' }
      const result = await ap.instance.execute()
      return { ok: true, task_id: result?.task_id }
    } catch (e: unknown) {
      // Catch the sentinel thrown by settings panels' execute()
      if (errMsg(e).includes('agent.error.no_execute_on_settings')) {
        return { error: 'agent.error.no_execute_on_settings' }
      }
      return { error: 'agent.error.tool_failed', detail: errMsg(e) }
    }
  },

  click_action: async ({ name }: { name: string }, ctx: DispatchCtx): Promise<ToolResult> => {
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

      if (ctx.signal?.aborted) return { error: 'agent.error.aborted' }
      const result = await ap.instance.invokeAction(name)
      return { ok: true, result }
    } catch (e: unknown) {
      return { error: 'agent.error.tool_failed', detail: errMsg(e) }
    }
  },

  get_task_status: async ({ task_id, run_id }: { task_id?: string; run_id?: string }): Promise<ToolResult> => {
    try {
      if (!task_id && !run_id) {
        return { error: 'agent.error.missing_args', missing: ['task_id or run_id'] }
      }
      useAgentStore().setCurrentAction('agent.banner.act.get_task_status', { task_id: task_id ?? run_id ?? '' })
      // pipeline run 聚合狀態
      if (run_id) {
        const { usePipelineStore } = await import('@/stores/pipeline')
        const pipeline = usePipelineStore()
        if (pipeline.currentRunId !== run_id || !pipeline.runSnapshot) {
          return { error: 'agent.error.tool_failed', detail: `run ${run_id} not found` }
        }
        const snap = pipeline.runSnapshot
        return {
          ok: true,
          run: {
            run_id,
            status: snap.status,
            done: snap.executions.filter(x => x.status === 'completed').length,
            failed: snap.executions.filter(x => x.status === 'failed').length,
            skipped: snap.executions.filter(x => x.status === 'skipped').length,
            total: snap.executions.length,
          },
        }
      }
      if (!task_id) {
        return { error: 'agent.error.missing_args', missing: ['task_id or run_id'] }
      }
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
    } catch (e: unknown) {
      return { error: 'agent.error.tool_failed', detail: errMsg(e) }
    }
  },

  create_pipeline: async (
    { name, nodes, edges }: {
      name?: string
      nodes: Array<{ id: string; kind: string; tool_key?: string; params?: Record<string, unknown> }>
      edges: Array<{ from: string; to: string }>
    },
    ctx: DispatchCtx,
  ): Promise<ToolResult> => {
    try {
      useAgentStore().setCurrentAction('agent.banner.act.create_pipeline', {})
      if (ctx.signal?.aborted) return { error: 'agent.error.aborted' }
      const [{ usePipelineStore }, { validateRecipe, normalizeParams }, { TOOL_REGISTRY }] = await Promise.all([
        import('@/stores/pipeline'),
        import('@/pipeline/recipe'),
        import('@/pipeline/registry'),
      ])
      const recipe = {
        version: 1 as const,
        name: name ?? '',
        nodes: (nodes ?? []).map((n, i) => ({
          id: String(n.id),
          kind: n.kind as 'input' | 'source' | 'tool',
          toolKey: n.tool_key,
          params: n.params ?? {},
          position: { x: 80 + i * 190, y: 180 + (i % 2) * 90 },
        })),
        edges: (edges ?? []).map(e => ({ from: String(e.from), to: String(e.to) })),
      }
      // 與畫布同一套驗證;錯誤結構化回饋供模型自我修正
      const errors = validateRecipe(recipe, TOOL_REGISTRY).filter(i => i.severity === 'error')
      if (errors.length > 0) {
        return {
          error: 'agent.error.invalid_pipeline',
          issues: errors.map(i => ({ code: i.code, node_id: i.nodeId, edge: i.edge, message: i.message })),
        }
      }
      // 參數正規化（剝未知、補 default）
      for (const n of recipe.nodes) {
        if (n.kind !== 'input' && n.toolKey && TOOL_REGISTRY[n.toolKey]) {
          n.params = normalizeParams(n.params, TOOL_REGISTRY[n.toolKey]).params
        }
      }
      const pipeline = usePipelineStore()
      if (pipeline.running) return { error: 'agent.error.pipeline_busy' }
      pipeline.recipe = recipe
      pipeline.currentRecipeId = null
      pipeline.selectedNodeId = null
      // 清掉舊 run 狀態,避免 get_task_status(舊 run_id) 讀到過期快照
      pipeline.currentRunId = null
      pipeline.runSnapshot = null
      const router = await resolveRouter()
      await router.push('/pipeline')
      return { ok: true, node_count: recipe.nodes.length, edge_count: recipe.edges.length }
    } catch (e: unknown) {
      return { error: 'agent.error.tool_failed', detail: errMsg(e) }
    }
  },

  run_pipeline: async (
    { input_file_ids }: { input_file_ids?: string[] },
    ctx: DispatchCtx,
  ): Promise<ToolResult> => {
    try {
      useAgentStore().setCurrentAction('agent.banner.act.run_pipeline', {})
      if (ctx.signal?.aborted) return { error: 'agent.error.aborted' }
      const { usePipelineStore } = await import('@/stores/pipeline')
      const pipeline = usePipelineStore()
      if (pipeline.running) return { error: 'agent.error.pipeline_busy' }
      if (input_file_ids && input_file_ids.length > 0) {
        const { getApiBase } = await import('@/composables/useApi')
        const resolved: Array<{ fileId: string; filename: string }> = []
        for (const fid of input_file_ids) {
          const res = await fetch(`${getApiBase()}/files/${fid}`)
          if (!res.ok) return { error: 'agent.error.tool_failed', detail: `file ${fid} not found` }
          const info = await res.json()
          resolved.push({ fileId: fid, filename: info.filename ?? '' })
        }
        pipeline.inputFiles = resolved
      }
      const errors = pipeline.errors
      if (errors.length > 0) {
        return {
          error: 'agent.error.invalid_pipeline',
          issues: errors.map(i => ({ code: i.code, node_id: i.nodeId, message: i.message })),
        }
      }
      if (!pipeline.canRun) {
        return { error: 'agent.error.pipeline_not_ready', detail: 'input files missing or graph empty' }
      }
      const runId = `run-${Date.now().toString(36)}`
      pipeline.currentRunId = runId
      pipeline.startRun().catch((e: unknown) => {
        // fire-and-forget:錯誤不回工具結果（已回 ok/run_id）,記 log 即可
        console.error('[agent] pipeline run failed', e)
      })
      return { ok: true, run_id: runId }
    } catch (e: unknown) {
      return { error: 'agent.error.tool_failed', detail: errMsg(e) }
    }
  },
}

// ─── Public dispatch function ─────────────────────────────────────────────────

// Required-field schema derived from TOOLS so dispatch() can short-circuit
// when a model emits a tool call with missing arguments (bug #15 model-quality
// case observed live with qwen3:8b emitting navigate_to({}) — would otherwise
// fall through to router.push(undefined) and a cryptic vue-router error).
const REQUIRED_BY_TOOL: Record<string, readonly string[]> = Object.fromEntries(
  TOOLS.map(t => {
    const params = t.parameters as { required?: string[] }
    return [t.name, Array.isArray(params?.required) ? params.required : []]
  }),
)

/**
 * Dispatch a tool call to the appropriate handler.  Safe to call from any
 * execution context; all store / router access inside the dispatchers is
 * lazy (see header note).
 */
export function dispatch(tc: ToolCall, ctx: DispatchCtx = {}): Promise<ToolResult> {
  const fn = dispatchers[tc.function.name]
  if (!fn) {
    return Promise.resolve({ error: 'agent.error.unknown_tool', tool: tc.function.name })
  }

  // Defense-in-depth: empty / whitespace `arguments` is treated as "{}"
  // (the SSE assembler already normalizes the wire path; this covers
  // direct callers / tests that bypass the assembler).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let args: any  // tool call args are runtime-validated by the ag-ui tool schema
  const raw = (tc.function.arguments ?? '').trim()
  if (!raw) {
    args = {}
  } else {
    try {
      args = JSON.parse(raw)
    } catch {
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

  return fn(args, ctx).catch((e: unknown) => ({
    error: 'agent.error.tool_failed',
    detail: errMsg(e),
  }))
}

// ─── Composable ───────────────────────────────────────────────────────────────

export function useAgentTools() {
  return { TOOLS, getTools, dispatch }
}
