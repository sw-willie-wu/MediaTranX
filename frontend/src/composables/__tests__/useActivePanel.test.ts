/**
 * Tests for useActivePanel (Wave 3 Task 3.2)
 *
 * Covers:
 *   1. view registered + panel registered + currentFunction set → returns entry
 *   2. view not registered → returns null
 *   3. view registered but currentFunction empty string → returns null
 *   4. panel id (viewId.fn) not in registry → returns null
 *   5. returned entry has correct panelId, schema, isMounted
 *   6. changing currentFunction → computed updates to new panel
 */

import { ref, nextTick, defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { describe, it, expect, beforeEach } from 'vitest'
import { viewRegistry, type ViewHandle } from '@/stores/viewRegistry'
import { panelRegistry, type PanelHandle, type PanelAgentSchema } from '@/stores/panelRegistry'
import { useActivePanel, type ActivePanelEntry } from '@/composables/useActivePanel'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeViewHandle(initialFn: string): ViewHandle {
  const currentFunction = ref(initialFn)
  return {
    currentFunction,
    setCurrentFunction: (id: string) => { currentFunction.value = id },
  }
}

function makeSchema(panelId: string): PanelAgentSchema {
  return {
    panelId,
    fields: [],
    actions: [],
    execute: null,
  }
}

function makePanelHandle(panelId: string): PanelHandle {
  const isMounted = ref(true)
  return {
    agentSchema: makeSchema(panelId),
    getCurrentValues: () => ({}),
    setField: (_f: string, v: unknown) => v,
    openField: () => {},
    execute: async () => ({}),
    isMultiSelect: () => false,
    isMounted,
  }
}

function makeRouter(initialPath = '/image') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/',         component: { template: '<div/>' } },
      { path: '/image',    component: { template: '<div/>' } },
      { path: '/video',    component: { template: '<div/>' } },
      { path: '/audio',    component: { template: '<div/>' } },
      { path: '/unknown',  component: { template: '<div/>' } },
    ],
  })
  router.push(initialPath)
  return router
}

// ─── Test lifecycle ───────────────────────────────────────────────────────────

beforeEach(() => {
  viewRegistry._clearAll()
  panelRegistry._clearAll()
})

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('useActivePanel', () => {
  it('view + panel registered + currentFunction set → returns ActivePanelEntry', async () => {
    const viewHandle = makeViewHandle('upscale')
    viewRegistry.register('image', viewHandle)
    panelRegistry.register('image.upscale', makePanelHandle('image.upscale'))

    const router = makeRouter('/image')
    await router.isReady()

    let entry: ActivePanelEntry | null | undefined = undefined
    const Comp = defineComponent({
      setup() {
        const active = useActivePanel()
        entry = active.value
        return {}
      },
      template: '<div></div>',
    })
    mount(Comp, { global: { plugins: [router] } })

    expect(entry).not.toBeNull()
    expect(entry!.panelId).toBe('image.upscale')
    expect(entry!.schema.panelId).toBe('image.upscale')
    expect(entry!.isMounted).toBe(true)
  })

  it('view not registered → returns null', async () => {
    // viewRegistry is empty
    panelRegistry.register('image.upscale', makePanelHandle('image.upscale'))

    const router = makeRouter('/image')
    await router.isReady()

    let entry: ActivePanelEntry | null | undefined = undefined
    const Comp = defineComponent({
      setup() {
        const active = useActivePanel()
        entry = active.value
        return {}
      },
      template: '<div></div>',
    })
    mount(Comp, { global: { plugins: [router] } })

    expect(entry).toBeNull()
  })

  it('view registered but currentFunction is empty string → returns null', async () => {
    const viewHandle = makeViewHandle('')  // empty
    viewRegistry.register('image', viewHandle)
    panelRegistry.register('image.upscale', makePanelHandle('image.upscale'))

    const router = makeRouter('/image')
    await router.isReady()

    let entry: ActivePanelEntry | null | undefined = undefined
    const Comp = defineComponent({
      setup() {
        const active = useActivePanel()
        entry = active.value
        return {}
      },
      template: '<div></div>',
    })
    mount(Comp, { global: { plugins: [router] } })

    expect(entry).toBeNull()
  })

  it('panel id not in registry → returns null', async () => {
    const viewHandle = makeViewHandle('upscale')
    viewRegistry.register('image', viewHandle)
    // panelRegistry is empty

    const router = makeRouter('/image')
    await router.isReady()

    let entry: ActivePanelEntry | null | undefined = undefined
    const Comp = defineComponent({
      setup() {
        const active = useActivePanel()
        entry = active.value
        return {}
      },
      template: '<div></div>',
    })
    mount(Comp, { global: { plugins: [router] } })

    expect(entry).toBeNull()
  })

  it('unknown route path → returns null', async () => {
    const viewHandle = makeViewHandle('upscale')
    viewRegistry.register('image', viewHandle)

    const router = makeRouter('/unknown')
    await router.isReady()

    let entry: ActivePanelEntry | null | undefined = undefined
    const Comp = defineComponent({
      setup() {
        const active = useActivePanel()
        entry = active.value
        return {}
      },
      template: '<div></div>',
    })
    mount(Comp, { global: { plugins: [router] } })

    expect(entry).toBeNull()
  })

  it('changing currentFunction → computed updates to new panel', async () => {
    const viewHandle = makeViewHandle('upscale')
    viewRegistry.register('image', viewHandle)
    panelRegistry.register('image.upscale', makePanelHandle('image.upscale'))
    panelRegistry.register('image.ocr',     makePanelHandle('image.ocr'))

    const router = makeRouter('/image')
    await router.isReady()

    const Comp = defineComponent({
      setup() {
        const active = useActivePanel()
        return { active }
      },
      template: '<div></div>',
    })
    const wrapper = mount(Comp, { global: { plugins: [router] } })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const vm = wrapper.vm as any

    expect(vm.active?.panelId).toBe('image.upscale')

    // Switch function
    viewHandle.setCurrentFunction('ocr')
    await nextTick()

    expect(vm.active?.panelId).toBe('image.ocr')
  })

  it('kebab subfunction id resolves to snake panelId (remove-bg → image.remove_bg)', async () => {
    // Subfunction ids live in the kebab "routing" namespace (remove-bg,
    // pdf-convert) while panels register under snake panelIds (image.remove_bg,
    // matching taskType/i18n). The bridge must normalize hyphens → underscores
    // or every multi-word subfunction resolves to null →
    // agent.error.panel_not_supported (regression: remove-bg / pdf-convert).
    const viewHandle = makeViewHandle('remove-bg')
    viewRegistry.register('image', viewHandle)
    panelRegistry.register('image.remove_bg', makePanelHandle('image.remove_bg'))

    const router = makeRouter('/image')
    await router.isReady()

    let entry: ActivePanelEntry | null | undefined = undefined
    const Comp = defineComponent({
      setup() {
        const active = useActivePanel()
        entry = active.value
        return {}
      },
      template: '<div></div>',
    })
    mount(Comp, { global: { plugins: [router] } })

    expect(entry).not.toBeNull()
    expect(entry!.panelId).toBe('image.remove_bg')
  })
})
