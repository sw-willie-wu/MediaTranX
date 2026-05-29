/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Tests for useAgentTools (Wave 3 Task 3.6)
 *
 * Strategy: each dispatcher is tested with a fake component context that
 * provides the required stores + router.  We use defineComponent + mount
 * (from @vue/test-utils) with a MemoryHistory router and a real Pinia instance
 * so that all stores (files, tasks) are available.
 *
 * Covers 2 cases minimum per dispatcher:
 *   navigate_to       — happy + unknown (always ok; router.push called)
 *   select_subfunction — view registered + setCurrentFunction called; view missing
 *   load_file         — file in store → ok; missing → file_not_found
 *   list_files        — returns mapped array; empty store → empty array
 *   open_dropdown     — panel active + isMounted → ok; panel not active → error
 *   set_field         — valid enum field → ok; unknown field → invalid_field
 *   click_execute     — settings panel (execute:null) → no_execute_on_settings; no panel → not_supported
 *   click_action      — valid action → ok; unknown action → invalid_action
 *   get_task_status   — task in store → ok; missing → tool_failed
 */

// @vitest-environment jsdom

import { ref, defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { describe, it, expect, beforeEach, vi } from 'vitest'

import { TOOLS, getTools, dispatch, _unwrapNestedValue, type ToolCall } from '@/composables/useAgentTools'
import { viewRegistry, type ViewHandle } from '@/stores/viewRegistry'
import { panelRegistry, type PanelHandle, type PanelAgentSchema } from '@/stores/panelRegistry'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeRouter(initialPath = '/image') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/',         component: { template: '<div/>' } },
      { path: '/image',    component: { template: '<div/>' } },
      { path: '/video',    component: { template: '<div/>' } },
      { path: '/audio',    component: { template: '<div/>' } },
      { path: '/document', component: { template: '<div/>' } },
      { path: '/settings', component: { template: '<div/>' } },
      { path: '/tasks',    component: { template: '<div/>' } },
    ],
  })
  router.push(initialPath)
  return router
}

function makeViewHandle(initialFn: string, validSubfunctions?: string[]): ViewHandle {
  const currentFunction = ref(initialFn)
  const handle: ViewHandle = {
    currentFunction,
    setCurrentFunction: (id: string) => { currentFunction.value = id },
  }
  if (validSubfunctions !== undefined) {
    handle.validSubfunctions = () => validSubfunctions
  }
  return handle
}

function makeSchema(panelId: string, executeNull = true): PanelAgentSchema {
  return {
    panelId,
    fields: [
      { name: 'model', type: 'enum', options: () => ['fast', 'quality'] },
    ],
    actions: [
      { name: 'reset', label: 'Reset' },
    ],
    execute: executeNull ? null : { requiresConfirm: false },
  }
}

function makePanelHandle(panelId: string, opts: {
  isMountedVal?: boolean
  executeNull?: boolean
  setFieldFn?: (f: string, v: unknown) => unknown
  invokeFn?: (name: string) => unknown
  executeFn?: () => Promise<{ task_id?: string }>
} = {}): PanelHandle {
  const isMounted = ref(opts.isMountedVal ?? true)
  const schema = makeSchema(panelId, opts.executeNull ?? true)
  return {
    agentSchema: schema,
    getCurrentValues: () => ({}),
    setField: opts.setFieldFn ?? ((_f, v) => v),
    openField: vi.fn(),
    execute: opts.executeFn ?? (() => Promise.resolve({ task_id: 'task-001' })),
    invokeAction: opts.invokeFn ?? ((_name) => ({ ok: true })),
    isMultiSelect: () => false,
    isMounted,
  }
}

/**
 * Run `fn(dispatch)` inside a component setup context.
 * Provides the router + pinia plugins so stores and composables work.
 */
async function withContext(
  router: ReturnType<typeof makeRouter>,
  fn: (d: typeof dispatch) => Promise<any>
): Promise<any> {
  await router.isReady()
  let result: any
  const Comp = defineComponent({
    async setup() {
      result = await fn(dispatch)
      return {}
    },
    template: '<div></div>',
  })
  mount(Comp, { global: { plugins: [router] } })
  // Allow async setup to settle
  await new Promise(r => setTimeout(r, 0))
  return result
}

function tc(name: string, args: object = {}): ToolCall {
  return {
    id: 'tc-' + name,
    type: 'function',
    function: { name, arguments: JSON.stringify(args) },
  }
}

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  setActivePinia(createPinia())
  viewRegistry._clearAll()
  panelRegistry._clearAll()
})

// ─── navigate_to ─────────────────────────────────────────────────────────────

describe('dispatch: navigate_to', () => {
  it('navigates to /video and returns ok:true', async () => {
    const router = makeRouter('/')
    let pushedRoute: string | undefined
    const origPush = router.push.bind(router)
    vi.spyOn(router, 'push').mockImplementation((loc: any) => {
      pushedRoute = loc
      return origPush(loc)
    })

    const result = await withContext(router, d => d(tc('navigate_to', { route: '/video' })))
    expect(result.ok).toBe(true)
    expect(pushedRoute).toBe('/video')
  })

  it('navigates to / (home) and returns ok:true', async () => {
    const router = makeRouter('/image')
    const result = await withContext(router, d => d(tc('navigate_to', { route: '/' })))
    expect(result.ok).toBe(true)
  })

  it('resolves the bare word "settings" to /settings', async () => {
    const router = makeRouter('/')
    let pushedRoute: string | undefined
    const origPush = router.push.bind(router)
    vi.spyOn(router, 'push').mockImplementation((loc: any) => { pushedRoute = loc; return origPush(loc) })

    const result = await withContext(router, d => d(tc('navigate_to', { route: 'settings' })))
    expect(result.ok).toBe(true)
    expect(pushedRoute).toBe('/settings')
  })

  it('maps the word "home" to "/" (not the dead /home route)', async () => {
    const router = makeRouter('/image')
    let pushedRoute: string | undefined
    const origPush = router.push.bind(router)
    vi.spyOn(router, 'push').mockImplementation((loc: any) => { pushedRoute = loc; return origPush(loc) })

    const result = await withContext(router, d => d(tc('navigate_to', { route: 'home' })))
    expect(result.ok).toBe(true)
    expect(pushedRoute).toBe('/')
  })

  it('rejects an unknown route with invalid_route + allowed, without navigating', async () => {
    const router = makeRouter('/image')
    const pushSpy = vi.spyOn(router, 'push')

    const result = await withContext(router, d => d(tc('navigate_to', { route: 'theme' })))
    expect(result.ok).toBeUndefined()
    expect(result.error).toBe('agent.error.invalid_route')
    expect(result.allowed).toContain('settings')
    expect(pushSpy).not.toHaveBeenCalled()   // a dead route must NOT navigate the app
  })
})

// ─── select_subfunction ───────────────────────────────────────────────────────

describe('dispatch: select_subfunction', () => {
  it('calls setCurrentFunction on the active view', async () => {
    const router = makeRouter('/image')
    await router.isReady()
    const vh = makeViewHandle('transcode')
    viewRegistry.register('image', vh)

    const result = await withContext(router, d => d(tc('select_subfunction', { name: 'upscale' })))
    expect(result.ok).toBe(true)
    expect(vh.currentFunction.value).toBe('upscale')
  })

  it('returns view_not_introspectable when no view registered', async () => {
    const router = makeRouter('/image')
    // viewRegistry is empty
    const result = await withContext(router, d => d(tc('select_subfunction', { name: 'upscale' })))
    expect(result.error).toBe('agent.error.view_not_introspectable')
  })

  // Bug #22: validation + dynamic enum tests
  it('Bug #22: returns invalid_subfunction with allowed list when name not in validSubfunctions', async () => {
    const router = makeRouter('/image')
    await router.isReady()
    const vh = makeViewHandle('transcode', ['transcode', 'upscale', 'remove-bg', 'ai-remove', 'adjust', 'filter', 'crop', 'ocr'])
    viewRegistry.register('image', vh)

    const result = await withContext(router, d => d(tc('select_subfunction', { name: 'convert' })))
    expect(result.error).toBe('agent.error.invalid_subfunction')
    expect(result.name).toBe('convert')
    expect(result.allowed).toContain('transcode')
    expect(result.allowed).not.toContain('convert')
    // currentFunction should NOT have changed
    expect(vh.currentFunction.value).toBe('transcode')
  })

  it('Bug #22: view without validSubfunctions passes any name through (backward compat)', async () => {
    const router = makeRouter('/image')
    await router.isReady()
    // makeViewHandle without second arg → no validSubfunctions
    const vh = makeViewHandle('transcode')
    viewRegistry.register('image', vh)

    const result = await withContext(router, d => d(tc('select_subfunction', { name: 'anything_goes' })))
    expect(result.ok).toBe(true)
    expect(vh.currentFunction.value).toBe('anything_goes')
  })

  it('Bug #22: valid name in validSubfunctions list succeeds', async () => {
    const router = makeRouter('/image')
    await router.isReady()
    const vh = makeViewHandle('transcode', ['transcode', 'upscale', 'ocr'])
    viewRegistry.register('image', vh)

    const result = await withContext(router, d => d(tc('select_subfunction', { name: 'ocr' })))
    expect(result.ok).toBe(true)
    expect(vh.currentFunction.value).toBe('ocr')
  })
})

// ─── load_file ────────────────────────────────────────────────────────────────

describe('dispatch: load_file', () => {
  it('sets current file when file exists in store', async () => {
    const router = makeRouter('/image')
    await router.isReady()

    let capturedId: string | null = null
    const Comp = defineComponent({
      async setup() {
        const filesStore = useFilesStore()
        // Inject a fake file into the store
        filesStore.files.set('file-abc', {
          id: 'file-abc',
          name: 'test.jpg',
          originalName: 'test.jpg',
          path: '',
          size: 100,
          mimeType: 'image/jpeg',
          type: 'image',
          createdAt: new Date(),
        })
        const origSet = filesStore.setCurrentFile.bind(filesStore)
        vi.spyOn(filesStore, 'setCurrentFile').mockImplementation((id) => {
          capturedId = id
          return origSet(id)
        })
        const result = await dispatch(tc('load_file', { file_id: 'file-abc' }))
        expect(result.ok).toBe(true)
        expect(capturedId).toBe('file-abc')
        return {}
      },
      template: '<div/>',
    })
    mount(Comp, { global: { plugins: [router] } })
    await new Promise(r => setTimeout(r, 0))
  })

  it('returns file_not_found when file does not exist and backend returns null', async () => {
    const router = makeRouter('/image')
    await router.isReady()

    const Comp = defineComponent({
      async setup() {
        const filesStore = useFilesStore()
        vi.spyOn(filesStore, 'getFileInfo').mockResolvedValue(null)
        const result = await dispatch(tc('load_file', { file_id: 'nonexistent-id' }))
        expect(result.error).toBe('agent.error.file_not_found')
        return {}
      },
      template: '<div/>',
    })
    mount(Comp, { global: { plugins: [router] } })
    await new Promise(r => setTimeout(r, 0))
  })
})

// ─── list_files ───────────────────────────────────────────────────────────────

describe('dispatch: list_files', () => {
  it('returns mapped file list from store', async () => {
    const router = makeRouter('/image')
    await router.isReady()

    const Comp = defineComponent({
      async setup() {
        const filesStore = useFilesStore()
        filesStore.files.set('f1', {
          id: 'f1', name: 'photo.jpg', originalName: 'photo.jpg',
          path: '', size: 500, mimeType: 'image/jpeg', type: 'image', createdAt: new Date(),
        })
        const result = await dispatch(tc('list_files'))
        expect(result.ok).toBe(true)
        expect(result.files).toHaveLength(1)
        expect(result.files[0].id).toBe('f1')
        expect(result.files[0].kind).toBe('image')
        return {}
      },
      template: '<div/>',
    })
    mount(Comp, { global: { plugins: [router] } })
    await new Promise(r => setTimeout(r, 0))
  })

  it('returns empty array when no files', async () => {
    const router = makeRouter('/image')
    const result = await withContext(router, d => d(tc('list_files')))
    expect(result.ok).toBe(true)
    expect(result.files).toEqual([])
  })
})

// ─── open_dropdown ────────────────────────────────────────────────────────────

describe('dispatch: open_dropdown', () => {
  it('calls openField on the active panel', async () => {
    const router = makeRouter('/image')
    await router.isReady()

    const vh = makeViewHandle('upscale')
    viewRegistry.register('image', vh)
    const openFieldFn = vi.fn()
    const handle = makePanelHandle('image.upscale')
    handle.openField = openFieldFn
    panelRegistry.register('image.upscale', handle)

    const result = await withContext(router, d => d(tc('open_dropdown', { field: 'model' })))
    expect(result.ok).toBe(true)
    expect(openFieldFn).toHaveBeenCalledWith('model')
  })

  it('returns panel_not_active when no panel active', async () => {
    const router = makeRouter('/image')
    // no view or panel registered
    const result = await withContext(router, d => d(tc('open_dropdown', { field: 'model' })))
    expect(result.error).toBe('agent.error.panel_not_active')
  })
})

// ─── set_field ────────────────────────────────────────────────────────────────

describe('dispatch: set_field', () => {
  it('sets a valid enum field (case-insensitive) and returns actual value', async () => {
    const router = makeRouter('/image')
    await router.isReady()

    const vh = makeViewHandle('upscale')
    viewRegistry.register('image', vh)
    const setFieldFn = vi.fn((_f: string, v: unknown) => v)
    const handle = makePanelHandle('image.upscale', { setFieldFn })
    panelRegistry.register('image.upscale', handle)

    // Use different case to test case-insensitive matching
    const result = await withContext(router, d => d(tc('set_field', { field: 'model', value: 'QUALITY' })))
    expect(result.ok).toBe(true)
    expect(result.actual).toBe('quality')  // matched canonical
    expect(setFieldFn).toHaveBeenCalledWith('model', 'quality')
  })

  it('returns invalid_field for unknown field name', async () => {
    const router = makeRouter('/image')
    await router.isReady()

    const vh = makeViewHandle('upscale')
    viewRegistry.register('image', vh)
    panelRegistry.register('image.upscale', makePanelHandle('image.upscale'))

    const result = await withContext(router, d => d(tc('set_field', { field: 'nonexistent', value: 'x' })))
    expect(result.error).toBe('agent.error.invalid_field')
    expect(result.allowed).toContain('model')
  })

  it('returns invalid_field for bad enum value', async () => {
    const router = makeRouter('/image')
    await router.isReady()

    const vh = makeViewHandle('upscale')
    viewRegistry.register('image', vh)
    panelRegistry.register('image.upscale', makePanelHandle('image.upscale'))

    const result = await withContext(router, d => d(tc('set_field', { field: 'model', value: 'ultrafast' })))
    expect(result.error).toBe('agent.error.invalid_field')
    expect(result.allowed).toEqual(['fast', 'quality'])
  })

  it('returns panel_not_supported when no panel registered', async () => {
    const router = makeRouter('/image')
    // nothing registered
    const result = await withContext(router, d => d(tc('set_field', { field: 'model', value: 'fast' })))
    expect(result.error).toBe('agent.error.panel_not_supported')
  })

  // Bug #23: qwen3.5 (and other non-strict local models) sometimes JSON-quote
  // their string enum values, emitting `value: "\"quality\""` over the wire
  // instead of `value: "quality"`. JSON.parse on the args turns that into the
  // literal four-char string `"quality"` (with the quote chars), which fails
  // the enum match. The dispatcher must strip one layer of JSON-quote-wrap
  // before the enum coerce so the model isn't punished for the quirk.
  it('Bug #23: unwraps JSON-quoted string enum value before matching', async () => {
    const router = makeRouter('/image')
    await router.isReady()

    const vh = makeViewHandle('upscale')
    viewRegistry.register('image', vh)
    const setFieldFn = vi.fn((_f: string, v: unknown) => v)
    const handle = makePanelHandle('image.upscale', { setFieldFn })
    panelRegistry.register('image.upscale', handle)

    // Value is the literal 9-char string  "quality"  (with the two quote chars),
    // which is what JSON.parse('"\\"quality\\""') produces from a qwen3.5 chunk.
    const result = await withContext(router, d => d(tc('set_field', { field: 'model', value: '"quality"' })))
    expect(result.ok).toBe(true)
    expect(result.actual).toBe('quality')
    expect(setFieldFn).toHaveBeenCalledWith('model', 'quality')
  })

  it('Bug #23: leaves a non-quoted string value untouched', async () => {
    const router = makeRouter('/image')
    await router.isReady()

    const vh = makeViewHandle('upscale')
    viewRegistry.register('image', vh)
    const setFieldFn = vi.fn((_f: string, v: unknown) => v)
    const handle = makePanelHandle('image.upscale', { setFieldFn })
    panelRegistry.register('image.upscale', handle)

    // Plain 'quality' must still match; the strip must not break the happy path.
    const result = await withContext(router, d => d(tc('set_field', { field: 'model', value: 'quality' })))
    expect(result.ok).toBe(true)
    expect(setFieldFn).toHaveBeenCalledWith('model', 'quality')
  })

  it('Bug #23: leaves a string that does not parse as JSON untouched', async () => {
    const router = makeRouter('/image')
    await router.isReady()

    const vh = makeViewHandle('upscale')
    viewRegistry.register('image', vh)
    const setFieldFn = vi.fn((_f: string, v: unknown) => v)
    const handle = makePanelHandle('image.upscale', { setFieldFn })
    panelRegistry.register('image.upscale', handle)

    // Mismatched outer quotes — not valid JSON, must NOT crash, must NOT strip.
    // Falls through to enum coerce and (rightly) gets invalid_field.
    const result = await withContext(router, d => d(tc('set_field', { field: 'model', value: '"quality' })))
    expect(result.error).toBe('agent.error.invalid_field')
  })
})

// ─── click_execute ────────────────────────────────────────────────────────────

describe('dispatch: click_execute', () => {
  it('returns no_execute_on_settings for settings panel (execute:null)', async () => {
    const router = makeRouter('/settings')
    await router.isReady()

    const vh = makeViewHandle('general')
    viewRegistry.register('settings', vh)
    // Settings panels have execute:null in schema
    const handle = makePanelHandle('settings.general', { executeNull: true })
    panelRegistry.register('settings.general', handle)

    const result = await withContext(router, d => d(tc('click_execute')))
    expect(result.error).toBe('agent.error.no_execute_on_settings')
  })

  it('calls execute() on non-settings panel and returns task_id', async () => {
    const router = makeRouter('/image')
    await router.isReady()

    const vh = makeViewHandle('upscale')
    viewRegistry.register('image', vh)
    const executeFn = vi.fn(async () => ({ task_id: 'task-xyz' }))
    const handle = makePanelHandle('image.upscale', {
      executeNull: false,
      executeFn,
    })
    panelRegistry.register('image.upscale', handle)

    // click_execute requires a loaded file (the underlying Apply button
    // is disabled without one) — inject one before invoking.
    const filesStore = useFilesStore()
    filesStore.files.set('file-go', {
      id: 'file-go', name: 'x.jpg', originalName: 'x.jpg', path: '',
      size: 100, mimeType: 'image/jpeg', type: 'image', createdAt: new Date(),
    })
    filesStore.setCurrentFile('file-go')

    const result = await withContext(router, d => d(tc('click_execute')))
    expect(result.ok).toBe(true)
    expect(result.task_id).toBe('task-xyz')
    expect(executeFn).toHaveBeenCalledOnce()
  })

  it('returns panel_not_supported when no panel active', async () => {
    const router = makeRouter('/image')
    const result = await withContext(router, d => d(tc('click_execute')))
    expect(result.error).toBe('agent.error.panel_not_supported')
  })

  // Regression (kebab→snake panelId bridge): the agent's subfunction id is
  // kebab-case (remove-bg) but the panel registers under a snake-case panelId
  // (image.remove_bg, matching taskType/i18n). click_execute goes through the
  // production _getActivePanel path; it must normalize and resolve the panel,
  // not return panel_not_supported. Before the fix executeFn never fired.
  it('resolves a kebab subfunction to its snake panelId (remove-bg → image.remove_bg)', async () => {
    const router = makeRouter('/image')
    await router.isReady()

    const vh = makeViewHandle('remove-bg', ['remove-bg', 'upscale', 'ocr'])
    viewRegistry.register('image', vh)
    const executeFn = vi.fn(async () => ({ task_id: 'task-rmbg' }))
    panelRegistry.register('image.remove_bg', makePanelHandle('image.remove_bg', {
      executeNull: false,
      executeFn,
    }))

    const filesStore = useFilesStore()
    filesStore.files.set('file-rmbg', {
      id: 'file-rmbg', name: 'x.jpg', originalName: 'x.jpg', path: '',
      size: 100, mimeType: 'image/jpeg', type: 'image', createdAt: new Date(),
    })
    filesStore.setCurrentFile('file-rmbg')

    const result = await withContext(router, d => d(tc('click_execute')))
    expect(result.error).not.toBe('agent.error.panel_not_supported')
    expect(result.ok).toBe(true)
    expect(result.task_id).toBe('task-rmbg')
    expect(executeFn).toHaveBeenCalledOnce()
  })

  // Bug: agent was free to fire click_execute on a panel whose Apply
  // button was disabled (no file loaded) and got back a phantom success.
  // The dispatcher must refuse universally — every tool panel needs an
  // active file (settings panels are already gated by execute:null).
  it('returns no_file_selected when no file is loaded in the store', async () => {
    const router = makeRouter('/image')
    await router.isReady()

    const vh = makeViewHandle('upscale')
    viewRegistry.register('image', vh)
    const executeFn = vi.fn(async () => ({ task_id: 'should-not-fire' }))
    panelRegistry.register('image.upscale', makePanelHandle('image.upscale', {
      executeNull: false,
      executeFn,
    }))

    // FilesStore.currentFile is null in a fresh pinia — that's the bug
    // condition the user reported.
    const result = await withContext(router, d => d(tc('click_execute')))
    expect(result.error).toBe('agent.error.no_file_selected')
    expect(executeFn).not.toHaveBeenCalled()
  })
})

// ─── click_action ─────────────────────────────────────────────────────────────

describe('dispatch: click_action', () => {
  it('invokes a registered action and returns result', async () => {
    const router = makeRouter('/image')
    await router.isReady()

    const vh = makeViewHandle('upscale')
    viewRegistry.register('image', vh)
    const invokeFn = vi.fn((_name: string) => ({ done: true }))
    const handle = makePanelHandle('image.upscale', { invokeFn })
    panelRegistry.register('image.upscale', handle)

    const result = await withContext(router, d => d(tc('click_action', { name: 'reset' })))
    expect(result.ok).toBe(true)
    expect(invokeFn).toHaveBeenCalledWith('reset')
  })

  it('returns invalid_action for unknown action name', async () => {
    const router = makeRouter('/image')
    await router.isReady()

    const vh = makeViewHandle('upscale')
    viewRegistry.register('image', vh)
    panelRegistry.register('image.upscale', makePanelHandle('image.upscale'))

    const result = await withContext(router, d => d(tc('click_action', { name: 'nonexistent_action' })))
    expect(result.error).toBe('agent.error.invalid_action')
    expect(result.allowed).toContain('reset')
  })

  it('returns panel_not_supported when no panel active', async () => {
    const router = makeRouter('/image')
    const result = await withContext(router, d => d(tc('click_action', { name: 'reset' })))
    expect(result.error).toBe('agent.error.panel_not_supported')
  })
})

// ─── get_task_status ──────────────────────────────────────────────────────────

describe('dispatch: get_task_status', () => {
  it('returns task status when task exists in store', async () => {
    const router = makeRouter('/tasks')
    await router.isReady()

    const Comp = defineComponent({
      async setup() {
        const tasksStore = useTaskStore()
        tasksStore.tasks.set('task-001', {
          taskId: 'task-001',
          taskType: 'image.upscale',
          status: 'completed',
          progress: 1,
          message: 'done',
          result: { output: 'out.jpg' },
          error: null,
          createdAt: new Date(),
          updatedAt: new Date(),
        })
        const result = await dispatch(tc('get_task_status', { task_id: 'task-001' }))
        expect(result.ok).toBe(true)
        expect(result.status.status).toBe('completed')
        expect(result.status.task_id).toBe('task-001')
        return {}
      },
      template: '<div/>',
    })
    mount(Comp, { global: { plugins: [router] } })
    await new Promise(r => setTimeout(r, 0))
  })

  it('returns tool_failed when task not found', async () => {
    const router = makeRouter('/tasks')
    const result = await withContext(router, d => d(tc('get_task_status', { task_id: 'missing-task' })))
    expect(result.error).toBe('agent.error.tool_failed')
    expect(result.detail).toContain('missing-task')
  })
})

// ─── dispatch: unknown tool ───────────────────────────────────────────────────

describe('dispatch: unknown tool', () => {
  it('returns unknown_tool error for unrecognised tool name', async () => {
    const router = makeRouter('/')
    const result = await withContext(router, d =>
      d({ id: 'x', type: 'function', function: { name: 'does_not_exist', arguments: '{}' } })
    )
    expect(result.error).toBe('agent.error.unknown_tool')
    expect(result.tool).toBe('does_not_exist')
  })

  it('returns tool_failed when arguments is invalid JSON', async () => {
    const router = makeRouter('/')
    const result = await withContext(router, d =>
      d({ id: 'x', type: 'function', function: { name: 'navigate_to', arguments: 'not-json' } })
    )
    expect(result.error).toBe('agent.error.tool_failed')
  })
})

// ─── getTools (Phase 2.A dynamic field enum) ─────────────────────────────────

describe('getTools (Phase 2.A dynamic field enum)', () => {
  it('returns set_field.field as free string when activePanelSchema is null', () => {
    const tools = getTools(null)
    const setField = tools.find(t => t.name === 'set_field')!
    const params = setField.parameters as any
    expect(params.properties.field).toEqual({ type: 'string' })
    expect(params.properties.field.enum).toBeUndefined()
  })

  it('returns set_field.field as enum when activePanelSchema has fields', () => {
    const panel: PanelAgentSchema = {
      panelId: 'x.y',
      fields: [
        { name: 'foo', type: 'enum', options: () => ['a', 'b'] },
        { name: 'bar', type: 'number', min: 0, max: 100 },
        { name: 'baz', type: 'bool' },
      ],
      actions: [],
      execute: { requiresConfirm: false },
    }
    const tools = getTools(panel)
    const setField = tools.find(t => t.name === 'set_field')!
    const params = setField.parameters as any
    expect(params.properties.field).toEqual({
      type: 'string',
      enum: ['foo', 'bar', 'baz'],
    })
  })

  it('returns set_field.field as free string when activePanelSchema has empty fields', () => {
    const panel: PanelAgentSchema = {
      panelId: 'x.y',
      fields: [],
      actions: [],
      execute: null,
    }
    const tools = getTools(panel)
    const setField = tools.find(t => t.name === 'set_field')!
    const params = setField.parameters as any
    expect(params.properties.field).toEqual({ type: 'string' })
  })

  it('preserves tool order regardless of activePanelSchema', () => {
    const names1 = getTools(null).map(t => t.name)
    const panel: PanelAgentSchema = {
      panelId: 'x.y',
      fields: [{ name: 'foo', type: 'string' }],
      actions: [],
      execute: null,
    }
    const names2 = getTools(panel).map(t => t.name)
    expect(names1).toEqual(['navigate_to', 'select_subfunction', 'load_file', 'list_files', 'open_dropdown', 'set_field', 'click_execute', 'click_action', 'get_task_status'])
    expect(names2).toEqual(names1)
  })

  it('TOOLS const equals getTools(null)', () => {
    expect(TOOLS).toEqual(getTools(null))
  })

  // Bug #22: select_subfunction dynamic enum via activeViewHandle
  it('Bug #22: select_subfunction.name is free string when activeViewHandle is null', () => {
    const tools = getTools(null, null)
    const selectSub = tools.find(t => t.name === 'select_subfunction')!
    const params = selectSub.parameters as any
    expect(params.properties.name).toEqual({ type: 'string' })
    expect(params.properties.name.enum).toBeUndefined()
  })

  it('Bug #22: select_subfunction.name becomes enum when view has validSubfunctions', () => {
    const fakeViewHandle: ViewHandle = {
      currentFunction: ref('transcode'),
      setCurrentFunction: (_id: string) => {},
      validSubfunctions: () => ['transcode', 'upscale', 'ocr'],
    }
    const tools = getTools(null, fakeViewHandle)
    const selectSub = tools.find(t => t.name === 'select_subfunction')!
    const params = selectSub.parameters as any
    expect(params.properties.name).toEqual({
      type: 'string',
      enum: ['transcode', 'upscale', 'ocr'],
    })
  })

  it('Bug #22: select_subfunction.name is free string when view has empty validSubfunctions', () => {
    const fakeViewHandle: ViewHandle = {
      currentFunction: ref('transcode'),
      setCurrentFunction: (_id: string) => {},
      validSubfunctions: () => [],
    }
    const tools = getTools(null, fakeViewHandle)
    const selectSub = tools.find(t => t.name === 'select_subfunction')!
    const params = selectSub.parameters as any
    expect(params.properties.name).toEqual({ type: 'string' })
    expect(params.properties.name.enum).toBeUndefined()
  })

  it('Bug #22: select_subfunction.name is free string when view has no validSubfunctions method', () => {
    const fakeViewHandle: ViewHandle = {
      currentFunction: ref('transcode'),
      setCurrentFunction: (_id: string) => {},
      // no validSubfunctions property
    }
    const tools = getTools(null, fakeViewHandle)
    const selectSub = tools.find(t => t.name === 'select_subfunction')!
    const params = selectSub.parameters as any
    expect(params.properties.name).toEqual({ type: 'string' })
    expect(params.properties.name.enum).toBeUndefined()
  })

  it('Bug #22: getTools with both panel schema and view handle produces correct tool array length', () => {
    const panel: PanelAgentSchema = {
      panelId: 'image.transcode',
      fields: [{ name: 'output_format', type: 'enum', options: () => ['png', 'jpg'] }],
      actions: [],
      execute: { requiresConfirm: true },
    }
    const fakeViewHandle: ViewHandle = {
      currentFunction: ref('transcode'),
      setCurrentFunction: (_id: string) => {},
      validSubfunctions: () => ['transcode', 'upscale'],
    }
    const tools = getTools(panel, fakeViewHandle)
    expect(tools).toHaveLength(9)
    const names = tools.map(t => t.name)
    expect(names).toEqual(['navigate_to', 'select_subfunction', 'load_file', 'list_files', 'open_dropdown', 'set_field', 'click_execute', 'click_action', 'get_task_status'])
  })
})

// ─── _unwrapNestedValue unit tests (Bug #21) ─────────────────────────────────

describe('_unwrapNestedValue (Bug #21 fix)', () => {
  it('passes scalar number through unchanged', () => {
    expect(_unwrapNestedValue('upscale_scale', 50)).toBe(50)
  })

  it('passes scalar string through unchanged', () => {
    expect(_unwrapNestedValue('model', 'quality')).toBe('quality')
  })

  it('unwraps {[field]: scalar} pattern', () => {
    expect(_unwrapNestedValue('model', { model: 'quality' })).toBe('quality')
  })

  it('unwraps {value: scalar} pattern', () => {
    expect(_unwrapNestedValue('upscale_scale', { value: 50 })).toBe(50)
  })

  it('does NOT unwrap when single key matches neither field nor "value"', () => {
    const obj = { other: 50 }
    expect(_unwrapNestedValue('upscale_scale', obj)).toBe(obj)
  })

  it('does NOT unwrap multi-key objects', () => {
    const obj = { foo: 1, bar: 2 }
    expect(_unwrapNestedValue('upscale_scale', obj)).toBe(obj)
  })

  it('passes null through unchanged', () => {
    expect(_unwrapNestedValue('field', null)).toBeNull()
  })

  it('passes array through unchanged', () => {
    const arr = [1, 2, 3]
    expect(_unwrapNestedValue('field', arr)).toBe(arr)
  })
})

// ─── set_field dispatcher unwrap integration (Bug #21) ───────────────────────

describe('set_field dispatcher: _unwrapNestedValue integration (Bug #21)', () => {
  function makeNumberSchema(panelId: string): import('@/stores/panelRegistry').PanelAgentSchema {
    return {
      panelId,
      fields: [
        { name: 'upscale_scale', type: 'number', min: 1, max: 4 },
        { name: 'grayscale', type: 'number', min: 0, max: 100 },
      ],
      actions: [],
      execute: { requiresConfirm: false },
    }
  }

  it('passes scalar value through to setField unchanged', async () => {
    const router = makeRouter('/image')
    await router.isReady()
    const vh = makeViewHandle('upscale')
    viewRegistry.register('image', vh)
    const setFieldFn = vi.fn((_f: string, v: unknown) => v)
    const handle = makePanelHandle('image.upscale', { setFieldFn })
    handle.agentSchema = makeNumberSchema('image.upscale')
    panelRegistry.register('image.upscale', handle)

    const result = await withContext(router, d =>
      d(tc('set_field', { field: 'upscale_scale', value: 2 }))
    )
    expect(result.ok).toBe(true)
    expect(setFieldFn).toHaveBeenCalledWith('upscale_scale', 2)
  })

  it('unwraps {[field]: scalar} pattern before passing to setField', async () => {
    const router = makeRouter('/image')
    await router.isReady()
    const vh = makeViewHandle('upscale')
    viewRegistry.register('image', vh)
    const setFieldFn = vi.fn((_f: string, v: unknown) => v)
    const handle = makePanelHandle('image.upscale', { setFieldFn })
    handle.agentSchema = makeNumberSchema('image.upscale')
    panelRegistry.register('image.upscale', handle)

    const result = await withContext(router, d =>
      d(tc('set_field', { field: 'upscale_scale', value: { upscale_scale: 2 } }))
    )
    expect(result.ok).toBe(true)
    expect(setFieldFn).toHaveBeenCalledWith('upscale_scale', 2)
  })

  it('unwraps {value: scalar} pattern before passing to setField', async () => {
    const router = makeRouter('/image')
    await router.isReady()
    const vh = makeViewHandle('upscale')
    viewRegistry.register('image', vh)
    const setFieldFn = vi.fn((_f: string, v: unknown) => v)
    const handle = makePanelHandle('image.upscale', { setFieldFn })
    handle.agentSchema = makeNumberSchema('image.upscale')
    panelRegistry.register('image.upscale', handle)

    const result = await withContext(router, d =>
      d(tc('set_field', { field: 'grayscale', value: { value: 50 } }))
    )
    expect(result.ok).toBe(true)
    expect(setFieldFn).toHaveBeenCalledWith('grayscale', 50)
  })

  it('does NOT unwrap when single key matches neither field nor "value"', async () => {
    const router = makeRouter('/image')
    await router.isReady()
    const vh = makeViewHandle('upscale')
    viewRegistry.register('image', vh)
    const setFieldFn = vi.fn((_f: string, v: unknown) => v)
    const handle = makePanelHandle('image.upscale', { setFieldFn })
    handle.agentSchema = makeNumberSchema('image.upscale')
    panelRegistry.register('image.upscale', handle)

    const result = await withContext(router, d =>
      d(tc('set_field', { field: 'upscale_scale', value: { other: 2 } }))
    )
    expect(result.ok).toBe(true)
    expect(setFieldFn).toHaveBeenCalledWith('upscale_scale', { other: 2 })
  })

  it('does NOT unwrap multi-key objects', async () => {
    const router = makeRouter('/image')
    await router.isReady()
    const vh = makeViewHandle('upscale')
    viewRegistry.register('image', vh)
    const setFieldFn = vi.fn((_f: string, v: unknown) => v)
    const handle = makePanelHandle('image.upscale', { setFieldFn })
    handle.agentSchema = makeNumberSchema('image.upscale')
    panelRegistry.register('image.upscale', handle)

    const result = await withContext(router, d =>
      d(tc('set_field', { field: 'upscale_scale', value: { foo: 1, bar: 2 } }))
    )
    expect(result.ok).toBe(true)
    expect(setFieldFn).toHaveBeenCalledWith('upscale_scale', { foo: 1, bar: 2 })
  })
})

// ─── settings.general panel smoke test (Task 3.5) ────────────────────────────

describe('settings.general panel registration smoke', () => {
  it('registers settings.general panel with theme + language fields', async () => {
    // Simulate what SettingsGeneral.vue does: register a panel in settings.general
    const schema: PanelAgentSchema = {
      panelId: 'settings.general',
      fields: [
        { name: 'theme', type: 'enum', options: () => ['system', 'dark', 'light'] },
        { name: 'language', type: 'enum', options: () => ['en', 'zh-TW'] },
      ],
      actions: [],
      execute: null,
    }
    const isMounted = ref(true)
    const themeVal = ref('system')
    panelRegistry.register('settings.general', {
      agentSchema: schema,
      getCurrentValues: () => ({ theme: themeVal.value, language: 'en' }),
      setField: (f: string, v: unknown) => {
        if (f === 'theme') { themeVal.value = v as string; return themeVal.value }
        return v
      },
      openField: () => {},
      execute: () => { throw new Error('agent.error.no_execute_on_settings') },
      isMultiSelect: () => false,
      isMounted,
    })

    const entry = panelRegistry.get('settings.general')
    expect(entry).toBeDefined()
    expect(entry!.agentSchema.execute).toBeNull()
    expect(entry!.agentSchema.fields.map(f => f.name)).toContain('theme')
    expect(entry!.agentSchema.fields.map(f => f.name)).toContain('language')
    expect(entry!.agentSchema.fields[0].options!()).toEqual(['system', 'dark', 'light'])

    // Test setField updates theme
    const actual = entry!.setField('theme', 'dark')
    expect(actual).toBe('dark')
    expect(themeVal.value).toBe('dark')

    // Test execute throws sentinel
    expect(() => entry!.execute()).toThrow('agent.error.no_execute_on_settings')
  })

  it('settings.agent panel has model + policy fields and clear_history action', async () => {
    const schema: PanelAgentSchema = {
      panelId: 'settings.agent',
      fields: [
        { name: 'model', type: 'enum', options: () => ['qwen3:8b'] },
        { name: 'policy', type: 'enum', options: () => ['auto', 'ask_all', 'custom'] },
      ],
      actions: [{ name: 'clear_history' }],
      execute: null,
    }
    panelRegistry.register('settings.agent', {
      agentSchema: schema,
      getCurrentValues: () => ({ model: 'qwen3:8b', policy: 'auto' }),
      setField: (_f, v) => v,
      openField: () => {},
      execute: () => { throw new Error('agent.error.no_execute_on_settings') },
      isMultiSelect: () => false,
      isMounted: ref(true),
    })

    const entry = panelRegistry.get('settings.agent')!
    expect(entry.agentSchema.execute).toBeNull()
    expect(entry.agentSchema.fields.map(f => f.name)).toContain('model')
    expect(entry.agentSchema.fields.map(f => f.name)).toContain('policy')
    expect(entry.agentSchema.actions.map(a => a.name)).toContain('clear_history')
  })
})
