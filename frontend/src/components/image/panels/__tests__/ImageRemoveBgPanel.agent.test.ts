/**
 * Smoke test — ImageRemoveBgPanel agent schema (Phase 2.A Task 2.5)
 *
 * Stub pattern. Single enum field, GPU confirm.
 */
import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeImageRemoveBgPanelStub(props: { isMultiSelect?: boolean } = {}) {
  const removeBgMode = ref('auto')

  const agentSchema = {
    panelId: 'image.remove_bg',
    fields: [
      { name: 'mode', type: 'enum' as const,
        options: () => ['auto', 'person', 'product', 'animal', 'anime'] },
    ],
    actions: [],
    execute: { requiresConfirm: true, label: 'panel.remove_bg.execute' },
  }

  const handle: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => props.isMultiSelect ?? false,
    getCurrentValues: () => ({ mode: removeBgMode.value }),
    setField: (field, value) => {
      switch (field) {
        case 'mode': removeBgMode.value = value as string; return removeBgMode.value
        default: throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() {
      useAgentPanelHost('image.remove_bg', handle)
      return {}
    },
    template: '<div></div>',
  })
}

describe('ImageRemoveBgPanel agent integration', () => {
  beforeEach(() => { panelRegistry._clearAll() })

  it('registers handle on mount', () => {
    mount(makeImageRemoveBgPanelStub())
    const handle = panelRegistry.get('image.remove_bg')
    expect(handle).toBeDefined()
    expect(handle!.agentSchema.panelId).toBe('image.remove_bg')
  })

  it('agentSchema fields list contains exactly [mode]', () => {
    mount(makeImageRemoveBgPanelStub())
    const handle = panelRegistry.get('image.remove_bg')!
    expect(handle.agentSchema.fields.map(f => f.name)).toEqual(['mode'])
    expect(handle.agentSchema.fields[0].type).toBe('enum')
  })

  it('mode field options returns 5 enum values', () => {
    mount(makeImageRemoveBgPanelStub())
    const handle = panelRegistry.get('image.remove_bg')!
    const opts = handle.agentSchema.fields[0].options!()
    expect(opts).toEqual(['auto', 'person', 'product', 'animal', 'anime'])
  })

  it('setField mode writes ref and returns the value', () => {
    mount(makeImageRemoveBgPanelStub())
    const handle = panelRegistry.get('image.remove_bg')!
    expect(handle.setField('mode', 'person')).toBe('person')
    expect(handle.getCurrentValues().mode).toBe('person')
  })

  it('setField mode accepts any string (panel-level — dispatcher guards invalid values)', () => {
    // Per spec §4.3 — panel setField is lax; dispatcher case-insensitive enum coerce + invalid_field guard handles BAD values upstream
    mount(makeImageRemoveBgPanelStub())
    const handle = panelRegistry.get('image.remove_bg')!
    expect(handle.setField('mode', 'BAD')).toBe('BAD')  // panel writes; dispatcher would have caught before this point
  })

  it('setField throws on unknown field NAME (not value)', () => {
    mount(makeImageRemoveBgPanelStub())
    const handle = panelRegistry.get('image.remove_bg')!
    expect(() => handle.setField('nonexistent', 'x')).toThrow(/Unknown field/)
  })

  it('getCurrentValues default is {mode: "auto"}', () => {
    mount(makeImageRemoveBgPanelStub())
    expect(panelRegistry.get('image.remove_bg')!.getCurrentValues()).toEqual({ mode: 'auto' })
  })

  it('execute requiresConfirm is true (GPU heavy)', () => {
    mount(makeImageRemoveBgPanelStub())
    expect(panelRegistry.get('image.remove_bg')!.agentSchema.execute!.requiresConfirm).toBe(true)
  })

  it('no actions declared', () => {
    mount(makeImageRemoveBgPanelStub())
    expect(panelRegistry.get('image.remove_bg')!.agentSchema.actions).toEqual([])
  })

  it('isMultiSelect honors prop + unregisters on unmount', () => {
    const w = mount(makeImageRemoveBgPanelStub({ isMultiSelect: true }))
    expect(panelRegistry.get('image.remove_bg')!.isMultiSelect()).toBe(true)
    w.unmount()
    expect(panelRegistry.get('image.remove_bg')).toBeUndefined()
  })
})
