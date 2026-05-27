/**
 * Tests for useViewHost (Wave 3 Task 3.1)
 *
 * Covers:
 *   1. mount → registry.get returns handle
 *   2. unmount → registry.get returns undefined
 *   3. re-register same viewId overwrites previous handle
 *   4. multiple views coexist independently
 */

import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { viewRegistry, type ViewHandle } from '@/stores/viewRegistry'
import { useViewHost } from '@/composables/useViewHost'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeHandle(initialFn = 'tab1'): ViewHandle {
  const currentFunction = ref(initialFn)
  return {
    currentFunction,
    setCurrentFunction: (id: string) => { currentFunction.value = id },
  }
}

/** Create a minimal component that calls useViewHost with the given args. */
function makeHostComponent(viewId: string, handle: ViewHandle) {
  return defineComponent({
    setup() {
      useViewHost(viewId, handle)
      return {}
    },
    template: '<div></div>',
  })
}

// ─── Test lifecycle ───────────────────────────────────────────────────────────

beforeEach(() => {
  viewRegistry._clearAll()
})

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('useViewHost', () => {
  it('mount component → registry.get returns handle', async () => {
    const handle = makeHandle('convert')
    const Comp = makeHostComponent('image', handle)
    mount(Comp)
    expect(viewRegistry.get('image')).toBe(handle)
  })

  it('unmount component → registry.get returns undefined', async () => {
    const handle = makeHandle('convert')
    const Comp = makeHostComponent('image', handle)
    const wrapper = mount(Comp)
    expect(viewRegistry.get('image')).toBe(handle)  // sanity check
    await wrapper.unmount()
    expect(viewRegistry.get('image')).toBeUndefined()
  })

  it('re-registering same viewId (second mount) overwrites previous handle', async () => {
    const h1 = makeHandle('tab1')
    const h2 = makeHandle('tab2')
    const Comp1 = makeHostComponent('video', h1)
    const Comp2 = makeHostComponent('video', h2)
    mount(Comp1)
    mount(Comp2)
    // Second registration wins
    expect(viewRegistry.get('video')).toBe(h2)
  })

  it('multiple views coexist independently', async () => {
    const hImage = makeHandle('upscale')
    const hAudio = makeHandle('transcribe')
    mount(makeHostComponent('image', hImage))
    mount(makeHostComponent('audio', hAudio))
    expect(viewRegistry.get('image')).toBe(hImage)
    expect(viewRegistry.get('audio')).toBe(hAudio)
  })

  it('handle currentFunction is mutable after registration', async () => {
    const handle = makeHandle('ocr')
    mount(makeHostComponent('image', handle))
    viewRegistry.get('image')!.setCurrentFunction('upscale')
    expect(handle.currentFunction.value).toBe('upscale')
  })
})
