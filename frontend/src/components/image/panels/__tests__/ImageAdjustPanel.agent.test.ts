/**
 * Smoke test — ImageAdjustPanel agent schema (Phase 2.A Task 2.3)
 *
 * Mirrors ImageUpscalePanel.agent.test.ts stub pattern. Verifies schema
 * shape + setField clamping + reset action + multi-select prop wiring +
 * AC-11 panel-switch invariant (unregister on unmount).
 */
import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeImageAdjustPanelStub(props: { isMultiSelect?: boolean } = {}) {
  const brightness = ref(100)
  const contrast   = ref(100)
  const saturation = ref(100)
  const sharpness  = ref(100)
  const hue        = ref(0)
  const warmth     = ref(0)

  function reset() {
    brightness.value = 100; contrast.value = 100; saturation.value = 100
    sharpness.value = 100; hue.value = 0; warmth.value = 0
  }

  const agentSchema = {
    panelId: 'image.adjust',
    fields: [
      { name: 'brightness', type: 'number' as const, min: 0,    max: 300, step: 1 },
      { name: 'contrast',   type: 'number' as const, min: 0,    max: 300, step: 1 },
      { name: 'saturation', type: 'number' as const, min: 0,    max: 300, step: 1 },
      { name: 'sharpness',  type: 'number' as const, min: 0,    max: 300, step: 1 },
      { name: 'hue',        type: 'number' as const, min: -180, max: 180, step: 1 },
      { name: 'warmth',     type: 'number' as const, min: -100, max: 100, step: 1 },
    ],
    actions: [{ name: 'reset', label: 'image.adjust.reset' }],
    execute: { requiresConfirm: false, label: 'panel.adjust.execute' },
  }

  const clamp = (v: unknown, lo: number, hi: number) => Math.min(Math.max(Number(v), lo), hi)

  const handleWithoutMounted: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => props.isMultiSelect ?? false,
    getCurrentValues: () => ({
      brightness: brightness.value, contrast: contrast.value, saturation: saturation.value,
      sharpness: sharpness.value, hue: hue.value, warmth: warmth.value,
    }),
    setField: (field, value) => {
      switch (field) {
        case 'brightness': { const c = clamp(value, 0, 300); brightness.value = c; return c }
        case 'contrast':   { const c = clamp(value, 0, 300); contrast.value = c;   return c }
        case 'saturation': { const c = clamp(value, 0, 300); saturation.value = c; return c }
        case 'sharpness':  { const c = clamp(value, 0, 300); sharpness.value = c;  return c }
        case 'hue':        { const c = clamp(value, -180, 180); hue.value = c;     return c }
        case 'warmth':     { const c = clamp(value, -100, 100); warmth.value = c;  return c }
        default: throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    invokeAction: (name) => { if (name === 'reset') reset() },
    execute: async () => ({}),
  }

  return defineComponent({
    setup() {
      useAgentPanelHost('image.adjust', handleWithoutMounted)
      return {}
    },
    template: '<div></div>',
  })
}

describe('ImageAdjustPanel agent integration', () => {
  beforeEach(() => { panelRegistry._clearAll() })

  it('registers handle on mount', () => {
    mount(makeImageAdjustPanelStub())
    const handle = panelRegistry.get('image.adjust')
    expect(handle).toBeDefined()
    expect(handle!.agentSchema.panelId).toBe('image.adjust')
  })

  it('agentSchema lists 6 fields in spec order, all type=number', () => {
    mount(makeImageAdjustPanelStub())
    const handle = panelRegistry.get('image.adjust')!
    expect(handle.agentSchema.fields.map(f => f.name)).toEqual([
      'brightness', 'contrast', 'saturation', 'sharpness', 'hue', 'warmth',
    ])
    expect(handle.agentSchema.fields.every(f => f.type === 'number')).toBe(true)
  })

  it('setField clamps brightness/contrast/saturation/sharpness to [0,300]', () => {
    mount(makeImageAdjustPanelStub())
    const handle = panelRegistry.get('image.adjust')!
    expect(handle.setField('brightness', 500)).toBe(300)
    expect(handle.setField('brightness', -100)).toBe(0)
    expect(handle.setField('contrast', 150)).toBe(150)
  })

  it('setField clamps hue to [-180,180]', () => {
    mount(makeImageAdjustPanelStub())
    const handle = panelRegistry.get('image.adjust')!
    expect(handle.setField('hue', 300)).toBe(180)
    expect(handle.setField('hue', -200)).toBe(-180)
  })

  it('setField clamps warmth to [-100,100]', () => {
    mount(makeImageAdjustPanelStub())
    const handle = panelRegistry.get('image.adjust')!
    expect(handle.setField('warmth', 200)).toBe(100)
    expect(handle.setField('warmth', -200)).toBe(-100)
  })

  it('setField throws on unknown field', () => {
    mount(makeImageAdjustPanelStub())
    const handle = panelRegistry.get('image.adjust')!
    expect(() => handle.setField('nonexistent', 1)).toThrow(/Unknown field/)
  })

  it('getCurrentValues snapshots defaults', () => {
    mount(makeImageAdjustPanelStub())
    const handle = panelRegistry.get('image.adjust')!
    expect(handle.getCurrentValues()).toEqual({
      brightness: 100, contrast: 100, saturation: 100, sharpness: 100, hue: 0, warmth: 0,
    })
  })

  it('execute returns empty object (no task_id needed by stub)', async () => {
    mount(makeImageAdjustPanelStub())
    const handle = panelRegistry.get('image.adjust')!
    expect(await handle.execute()).toEqual({})
  })

  it('execute requiresConfirm is false (CPU-only)', () => {
    mount(makeImageAdjustPanelStub())
    expect(panelRegistry.get('image.adjust')!.agentSchema.execute!.requiresConfirm).toBe(false)
  })

  it('reset action declared with i18n label', () => {
    mount(makeImageAdjustPanelStub())
    expect(panelRegistry.get('image.adjust')!.agentSchema.actions).toEqual([
      { name: 'reset', label: 'image.adjust.reset' },
    ])
  })

  it('invokeAction("reset") resets all 6 fields', () => {
    mount(makeImageAdjustPanelStub())
    const handle = panelRegistry.get('image.adjust')!
    handle.setField('brightness', 50); handle.setField('warmth', 80)
    handle.invokeAction!('reset')
    expect(handle.getCurrentValues()).toEqual({
      brightness: 100, contrast: 100, saturation: 100, sharpness: 100, hue: 0, warmth: 0,
    })
  })

  it('isMultiSelect honors prop', () => {
    mount(makeImageAdjustPanelStub({ isMultiSelect: true }))
    expect(panelRegistry.get('image.adjust')!.isMultiSelect()).toBe(true)
  })

  it('unregisters on unmount', () => {
    const w = mount(makeImageAdjustPanelStub())
    expect(panelRegistry.get('image.adjust')).toBeDefined()
    w.unmount()
    expect(panelRegistry.get('image.adjust')).toBeUndefined()
  })

  // AC-11 — KeepAlive-aware panel switch: unmount of one panel must not
  // touch another panel's registration (registry independence invariant)
  it('switching panels leaves the other panel intact in registry (AC-11)', () => {
    const w1 = mount(makeImageAdjustPanelStub())
    expect(panelRegistry.get('image.adjust')).toBeDefined()

    // Simulate a second panel (e.g. image.filter) being concurrently registered
    // — directly register a minimal handle without a full stub, to avoid
    // pulling Task 2.4's filter stub into this file.
    const otherHandle = {
      agentSchema: { panelId: 'image.other', fields: [], actions: [], execute: null },
      isMultiSelect: () => false,
      getCurrentValues: () => ({}),
      setField: (_f: string, v: unknown) => v,
      openField: (_f: string) => {},
      execute: async () => ({}),
      isMounted: { value: true } as ReturnType<typeof ref<boolean>>,
    }
    panelRegistry.register('image.other', otherHandle as unknown as PanelHandle)
    expect(panelRegistry.get('image.other')).toBeDefined()

    // Switch (unmount adjust, simulating user navigation away from adjust)
    w1.unmount()
    expect(panelRegistry.get('image.adjust')).toBeUndefined()  // adjust gone
    expect(panelRegistry.get('image.other')).toBeDefined()      // other untouched
  })
})
