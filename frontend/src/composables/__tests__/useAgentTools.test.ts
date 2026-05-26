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

import { dispatch, type ToolCall } from '@/composables/useAgentTools'
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

function makeViewHandle(initialFn: string): ViewHandle {
  const currentFunction = ref(initialFn)
  return {
    currentFunction,
    setCurrentFunction: (id: string) => { currentFunction.value = id },
  }
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
})

// ─── select_subfunction ───────────────────────────────────────────────────────

describe('dispatch: select_subfunction', () => {
  it('calls setCurrentFunction on the active view', async () => {
    const router = makeRouter('/image')
    await router.isReady()
    const vh = makeViewHandle('convert')
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
