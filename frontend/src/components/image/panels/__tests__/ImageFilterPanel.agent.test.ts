/**
 * Smoke test — ImageFilterPanel agent schema (Phase 2.A Task 2.4)
 *
 * Mirrors Task 2.3 stub pattern. 5 filter fields + reset action.
 */
import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeImageFilterPanelStub(props: { isMultiSelect?: boolean } = {}) {
  const grayscale = ref(0)
  const sepia     = ref(0)
  const invert    = ref(0)
  const blur      = ref(0)
  const vignette  = ref(0)

  function reset() {
    grayscale.value = 0; sepia.value = 0; invert.value = 0
    blur.value = 0; vignette.value = 0
  }

  const agentSchema = {
    panelId: 'image.filter',
    fields: [
      { name: 'grayscale', type: 'number' as const, min: 0, max: 100, step: 1 },
      { name: 'sepia',     type: 'number' as const, min: 0, max: 100, step: 1 },
      { name: 'invert',    type: 'number' as const, min: 0, max: 100, step: 1 },
      { name: 'blur',      type: 'number' as const, min: 0, max: 20,  step: 1 },
      { name: 'vignette',  type: 'number' as const, min: 0, max: 100, step: 1 },
    ],
    actions: [{ name: 'reset', label: 'image.filter.reset' }],
    execute: { requiresConfirm: false, label: 'panel.filter.execute' },
  }

  const clamp = (v: unknown, lo: number, hi: number) => Math.min(Math.max(Number(v), lo), hi)

  const handleWithoutMounted: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => props.isMultiSelect ?? false,
    getCurrentValues: () => ({
      grayscale: grayscale.value, sepia: sepia.value, invert: invert.value,
      blur: blur.value, vignette: vignette.value,
    }),
    setField: (field, value) => {
      switch (field) {
        case 'grayscale': { const c = clamp(value, 0, 100); grayscale.value = c; return c }
        case 'sepia':     { const c = clamp(value, 0, 100); sepia.value = c;     return c }
        case 'invert':    { const c = clamp(value, 0, 100); invert.value = c;    return c }
        case 'blur':      { const c = clamp(value, 0, 20);  blur.value = c;      return c }
        case 'vignette':  { const c = clamp(value, 0, 100); vignette.value = c;  return c }
        default: throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    invokeAction: (name) => { if (name === 'reset') reset() },
    execute: async () => ({}),
  }

  return defineComponent({
    setup() {
      useAgentPanelHost('image.filter', handleWithoutMounted)
      return {}
    },
    template: '<div></div>',
  })
}

describe('ImageFilterPanel agent integration', () => {
  beforeEach(() => { panelRegistry._clearAll() })

  it('registers handle on mount', () => {
    mount(makeImageFilterPanelStub())
    const handle = panelRegistry.get('image.filter')
    expect(handle).toBeDefined()
    expect(handle!.agentSchema.panelId).toBe('image.filter')
  })

  it('agentSchema lists 5 fields in spec order, all type=number', () => {
    mount(makeImageFilterPanelStub())
    const handle = panelRegistry.get('image.filter')!
    expect(handle.agentSchema.fields.map(f => f.name)).toEqual([
      'grayscale', 'sepia', 'invert', 'blur', 'vignette',
    ])
    expect(handle.agentSchema.fields.every(f => f.type === 'number')).toBe(true)
  })

  it('setField clamps 4 percent fields to [0,100]', () => {
    mount(makeImageFilterPanelStub())
    const handle = panelRegistry.get('image.filter')!
    expect(handle.setField('grayscale', 200)).toBe(100)
    expect(handle.setField('sepia', -50)).toBe(0)
    expect(handle.setField('invert', 50)).toBe(50)
    expect(handle.setField('vignette', 150)).toBe(100)
  })

  it('setField clamps blur to [0,20]', () => {
    mount(makeImageFilterPanelStub())
    const handle = panelRegistry.get('image.filter')!
    expect(handle.setField('blur', 50)).toBe(20)
    expect(handle.setField('blur', -5)).toBe(0)
    expect(handle.setField('blur', 10)).toBe(10)
  })

  it('setField throws on unknown field', () => {
    mount(makeImageFilterPanelStub())
    const handle = panelRegistry.get('image.filter')!
    expect(() => handle.setField('nonexistent', 1)).toThrow(/Unknown field/)
  })

  it('getCurrentValues snapshots defaults (all 0)', () => {
    mount(makeImageFilterPanelStub())
    const handle = panelRegistry.get('image.filter')!
    expect(handle.getCurrentValues()).toEqual({
      grayscale: 0, sepia: 0, invert: 0, blur: 0, vignette: 0,
    })
  })

  it('execute returns empty object', async () => {
    mount(makeImageFilterPanelStub())
    expect(await panelRegistry.get('image.filter')!.execute()).toEqual({})
  })

  it('execute requiresConfirm is false (CPU-only)', () => {
    mount(makeImageFilterPanelStub())
    expect(panelRegistry.get('image.filter')!.agentSchema.execute!.requiresConfirm).toBe(false)
  })

  it('reset action declared with i18n label', () => {
    mount(makeImageFilterPanelStub())
    expect(panelRegistry.get('image.filter')!.agentSchema.actions).toEqual([
      { name: 'reset', label: 'image.filter.reset' },
    ])
  })

  it('invokeAction("reset") resets all 5 fields to 0', () => {
    mount(makeImageFilterPanelStub())
    const handle = panelRegistry.get('image.filter')!
    handle.setField('grayscale', 80); handle.setField('blur', 10)
    handle.invokeAction!('reset')
    expect(handle.getCurrentValues()).toEqual({
      grayscale: 0, sepia: 0, invert: 0, blur: 0, vignette: 0,
    })
  })

  it('isMultiSelect honors prop', () => {
    mount(makeImageFilterPanelStub({ isMultiSelect: true }))
    expect(panelRegistry.get('image.filter')!.isMultiSelect()).toBe(true)
  })

  it('unregisters on unmount', () => {
    const w = mount(makeImageFilterPanelStub())
    expect(panelRegistry.get('image.filter')).toBeDefined()
    w.unmount()
    expect(panelRegistry.get('image.filter')).toBeUndefined()
  })
})
