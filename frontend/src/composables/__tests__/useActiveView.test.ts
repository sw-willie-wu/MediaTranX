/**
 * Tests for useActiveView + deriveViewId (Wave 3 Task 3.1)
 *
 * Covers:
 *   A. deriveViewId pure function — all 7 known paths + sub-paths + unknown
 *   B. useActiveView computed reactivity:
 *      1. view registered at correct viewId → returns handle
 *      2. view not registered → returns null
 *      3. route changes → computed updates
 *      4. unknown route path → returns null
 */

import { ref, nextTick } from 'vue'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { describe, it, expect, beforeEach } from 'vitest'
import { viewRegistry, type ViewHandle } from '@/stores/viewRegistry'
import { deriveViewId, useActiveView } from '@/composables/useActiveView'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeHandle(initialFn = 'tab1'): ViewHandle {
  const currentFunction = ref(initialFn)
  return {
    currentFunction,
    setCurrentFunction: (id: string) => { currentFunction.value = id },
  }
}

function makeRouter(initialPath = '/') {
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
      { path: '/unknown',  component: { template: '<div/>' } },
    ],
  })
  router.push(initialPath)
  return router
}

// ─── Test lifecycle ───────────────────────────────────────────────────────────

beforeEach(() => {
  viewRegistry._clearAll()
})

// ─── A. deriveViewId unit tests ───────────────────────────────────────────────

describe('deriveViewId', () => {
  it.each([
    ['/image',             'image'],
    ['/image/sub',         'image'],
    ['/video',             'video'],
    ['/audio',             'audio'],
    ['/document',          'document'],
    ['/settings',          'settings'],
    ['/tasks',             'tasks'],
    ['/',                  'home'],
    ['',                   'home'],
    ['/unknown',           null],
    ['/not-a-real-route',  null],
  ])('deriveViewId("%s") → %s', (path, expected) => {
    expect(deriveViewId(path)).toBe(expected)
  })
})

// ─── B. useActiveView composable tests ───────────────────────────────────────

describe('useActiveView', () => {
  it('view registered + route matches → computed returns handle', async () => {
    const handle = makeHandle('upscale')
    viewRegistry.register('image', handle)

    const router = makeRouter('/image')
    await router.isReady()

    let capturedHandle: ViewHandle | null = null
    const Comp = defineComponent({
      setup() {
        const activeView = useActiveView()
        capturedHandle = activeView.value
        return {}
      },
      template: '<div></div>',
    })
    mount(Comp, { global: { plugins: [router] } })

    expect(capturedHandle).toBe(handle)
  })

  it('view not registered → returns null', async () => {
    // No registration — registry is empty
    const router = makeRouter('/image')
    await router.isReady()

    let capturedHandle: ViewHandle | null | undefined = undefined
    const Comp = defineComponent({
      setup() {
        const activeView = useActiveView()
        capturedHandle = activeView.value
        return {}
      },
      template: '<div></div>',
    })
    mount(Comp, { global: { plugins: [router] } })

    expect(capturedHandle).toBeNull()
  })

  it('unknown route path → returns null', async () => {
    const router = makeRouter('/unknown')
    await router.isReady()

    let capturedHandle: ViewHandle | null | undefined = undefined
    const Comp = defineComponent({
      setup() {
        const activeView = useActiveView()
        capturedHandle = activeView.value
        return {}
      },
      template: '<div></div>',
    })
    mount(Comp, { global: { plugins: [router] } })

    expect(capturedHandle).toBeNull()
  })

  it('computed updates when route changes', async () => {
    const imageHandle = makeHandle('upscale')
    const videoHandle = makeHandle('subtitle')
    viewRegistry.register('image', imageHandle)
    viewRegistry.register('video', videoHandle)

    const router = makeRouter('/image')
    await router.isReady()

    const result = ref<ViewHandle | null>(null)
    const Comp = defineComponent({
      setup() {
        const activeView = useActiveView()
        result.value = activeView.value
        // expose the computed for assertions
        return { activeView }
      },
      template: '<div></div>',
    })
    const wrapper = mount(Comp, { global: { plugins: [router] } })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const vm = wrapper.vm as any

    expect(vm.activeView).toBe(imageHandle)

    await router.push('/video')
    await nextTick()

    expect(vm.activeView).toBe(videoHandle)
  })
})
