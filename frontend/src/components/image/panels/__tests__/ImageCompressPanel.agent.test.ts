/**
 * Smoke test — ImageCompressPanel agent schema
 *
 * Verifies:
 *   - After mount, panelRegistry.get('image.compress') returns a handle
 *   - agentSchema.panelId === 'image.compress'
 *   - getCurrentValues() returns all schema field names
 *   - strength field is present
 *   - GIF advanced fields (gif_colors, gif_frame_drop, gif_optimize_transparency, gif_coalesce) are present
 *   - visibleWhen gates on gif input (false when non-GIF, true when GIF)
 *   - setField clamping works
 */

import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeImageCompressPanelStub(gifInput = false) {
  const strength = ref(75)
  const gifColors = ref(128)
  const gifFrameDrop = ref(0)
  const gifOptimizeTransparency = ref(true)
  const gifCoalesce = ref(false)
  const isGif = ref(gifInput)

  const agentSchema = {
    panelId: 'image.compress',
    fields: [
      { name: 'strength', type: 'number' as const, min: 1, max: 100, step: 1 },
      { name: 'gif_colors', type: 'number' as const, min: 2, max: 256, step: 1,
        visibleWhen: () => isGif.value },
      { name: 'gif_frame_drop', type: 'enum' as const,
        options: () => ['0', '2', '3', '4'],
        visibleWhen: () => isGif.value },
      { name: 'gif_optimize_transparency', type: 'bool' as const,
        visibleWhen: () => isGif.value },
      { name: 'gif_coalesce', type: 'bool' as const,
        visibleWhen: () => isGif.value },
    ],
    actions: [],
    execute: { requiresConfirm: true, label: 'panel.compress.execute' },
  }

  const handleWithoutMounted: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => false,
    getCurrentValues: () => ({
      strength: strength.value,
      gif_colors: gifColors.value,
      gif_frame_drop: gifFrameDrop.value,
      gif_optimize_transparency: gifOptimizeTransparency.value,
      gif_coalesce: gifCoalesce.value,
    }),
    setField: (field, value) => {
      switch (field) {
        case 'strength': {
          const clamped = Math.min(Math.max(Number(value), 1), 100)
          strength.value = clamped
          return clamped
        }
        case 'gif_colors': {
          const clamped = Math.min(Math.max(Number(value), 2), 256)
          gifColors.value = clamped
          return clamped
        }
        case 'gif_frame_drop':
          gifFrameDrop.value = Number(value)
          return gifFrameDrop.value
        case 'gif_optimize_transparency':
          gifOptimizeTransparency.value = Boolean(value)
          return gifOptimizeTransparency.value
        case 'gif_coalesce':
          gifCoalesce.value = Boolean(value)
          return gifCoalesce.value
        default:
          throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  const component = defineComponent({
    setup() {
      useAgentPanelHost('image.compress', handleWithoutMounted)
      return {}
    },
    template: '<div></div>',
  })

  return { component, isGif }
}

beforeEach(() => { panelRegistry._clearAll() })

describe('ImageCompressPanel agent schema smoke', () => {
  it('mount → panelRegistry.get returns a handle', () => {
    const { component } = makeImageCompressPanelStub()
    mount(component)
    expect(panelRegistry.get('image.compress')).toBeDefined()
  })

  it('agentSchema.panelId === "image.compress"', () => {
    const { component } = makeImageCompressPanelStub()
    mount(component)
    const handle = panelRegistry.get('image.compress')!
    expect(handle.agentSchema.panelId).toBe('image.compress')
  })

  it('getCurrentValues() returns all schema field names', () => {
    const { component } = makeImageCompressPanelStub()
    mount(component)
    const handle = panelRegistry.get('image.compress')!
    const values = handle.getCurrentValues()
    for (const field of handle.agentSchema.fields) {
      expect(values).toHaveProperty(field.name)
    }
  })

  it('strength field present with correct type and range', () => {
    const { component } = makeImageCompressPanelStub()
    mount(component)
    const handle = panelRegistry.get('image.compress')!
    const strengthField = handle.agentSchema.fields.find(f => f.name === 'strength')
    expect(strengthField).toBeDefined()
    expect(strengthField?.type).toBe('number')
    expect(strengthField?.min).toBe(1)
    expect(strengthField?.max).toBe(100)
  })

  it('GIF advanced fields present in schema', () => {
    const { component } = makeImageCompressPanelStub()
    mount(component)
    const handle = panelRegistry.get('image.compress')!
    const gifFieldNames = ['gif_colors', 'gif_frame_drop', 'gif_optimize_transparency', 'gif_coalesce']
    for (const name of gifFieldNames) {
      expect(handle.agentSchema.fields.find(f => f.name === name), `${name} should be in schema`).toBeDefined()
    }
  })

  it('visibleWhen for GIF fields returns false when input is not GIF', () => {
    const { component } = makeImageCompressPanelStub(false)
    mount(component)
    const handle = panelRegistry.get('image.compress')!
    const gifFields = handle.agentSchema.fields.filter(f => f.name !== 'strength')
    for (const field of gifFields) {
      expect(field.visibleWhen?.(), `${field.name} visibleWhen should be false for non-GIF`).toBe(false)
    }
  })

  it('visibleWhen for GIF fields returns true when input is GIF', () => {
    const { component, isGif } = makeImageCompressPanelStub(false)
    mount(component)
    isGif.value = true
    const handle = panelRegistry.get('image.compress')!
    const gifFields = handle.agentSchema.fields.filter(f => f.name !== 'strength')
    for (const field of gifFields) {
      expect(field.visibleWhen?.(), `${field.name} visibleWhen should be true for GIF`).toBe(true)
    }
  })

  it('setField strength = 50 → returns 50', () => {
    const { component } = makeImageCompressPanelStub()
    mount(component)
    const handle = panelRegistry.get('image.compress')!
    expect(handle.setField('strength', 50)).toBe(50)
  })

  it('setField strength > 100 → clamped to 100', () => {
    const { component } = makeImageCompressPanelStub()
    mount(component)
    const handle = panelRegistry.get('image.compress')!
    expect(handle.setField('strength', 150)).toBe(100)
  })

  it('setField gif_colors clamped within 2–256', () => {
    const { component } = makeImageCompressPanelStub()
    mount(component)
    const handle = panelRegistry.get('image.compress')!
    expect(handle.setField('gif_colors', 300)).toBe(256)
    expect(handle.setField('gif_colors', 1)).toBe(2)
  })
})
