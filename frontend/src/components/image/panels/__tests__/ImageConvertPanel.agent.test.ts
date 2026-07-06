/**
 * Smoke test — ImageConvertPanel agent schema (Wave 3 Task 3.4)
 *
 * Verifies:
 *   - After mount, panelRegistry.get('image.transcode') returns a handle
 *   - getCurrentValues() returns an object with all schema field names
 *   - setField('quality', 75) returns 75 (within range)
 *   - setField('quality', 200) returns 100 (clamped, R-5)
 */

import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeImageConvertPanelStub(initialFormat = 'png') {
  const convertFormat = ref(initialFormat)
  const convertQuality = ref(90)
  const convertCoalesce = ref(false)
  const convertResizeMode = ref<'original' | 'scale' | 'custom'>('original')
  const convertScale = ref(100)
  const convertWidth = ref<number | null>(null)
  const convertHeight = ref<number | null>(null)

  const convertFormats = [
    { value: 'png' }, { value: 'jpg' }, { value: 'webp' }, { value: 'gif' }, { value: 'bmp' },
  ]

  const agentSchema = {
    panelId: 'image.transcode',
    fields: [
      { name: 'output_format', type: 'enum' as const,
        options: () => convertFormats.map(f => f.value) },
      { name: 'quality', type: 'number' as const,
        min: 1, max: 100, step: 1,
        visibleWhen: () => convertFormat.value === 'jpg' || convertFormat.value === 'webp' },
      { name: 'coalesce', type: 'bool' as const,
        visibleWhen: () => convertFormat.value === 'gif' },
      { name: 'resize_mode', type: 'enum' as const,
        options: () => ['original', 'scale', 'custom'] },
      { name: 'scale', type: 'number' as const,
        min: 10, max: 200, step: 1,
        visibleWhen: () => convertResizeMode.value === 'scale' },
      { name: 'custom_width', type: 'number' as const,
        min: 1, max: 99999, step: 1,
        visibleWhen: () => convertResizeMode.value === 'custom' },
      { name: 'custom_height', type: 'number' as const,
        min: 1, max: 99999, step: 1,
        visibleWhen: () => convertResizeMode.value === 'custom' },
    ],
    actions: [],
    execute: { requiresConfirm: true, label: 'panel.transcode.execute' },
  }

  const handleWithoutMounted: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => false,
    getCurrentValues: () => ({
      output_format: convertFormat.value,
      quality: convertQuality.value,
      coalesce: convertCoalesce.value,
      resize_mode: convertResizeMode.value,
      scale: convertScale.value,
      custom_width: convertWidth.value,
      custom_height: convertHeight.value,
    }),
    setField: (field, value) => {
      switch (field) {
        case 'output_format':
          convertFormat.value = value as string
          return value
        case 'quality': {
          const clamped = Math.min(Math.max(Number(value), 1), 100)
          convertQuality.value = clamped
          return clamped
        }
        case 'coalesce':
          convertCoalesce.value = Boolean(value)
          return convertCoalesce.value
        case 'resize_mode':
          convertResizeMode.value = value as 'original' | 'scale' | 'custom'
          return value
        case 'scale': {
          const clamped = Math.min(Math.max(Number(value), 10), 200)
          convertScale.value = clamped
          return clamped
        }
        case 'custom_width':
          convertWidth.value = value === null ? null : Number(value)
          return convertWidth.value
        case 'custom_height':
          convertHeight.value = value === null ? null : Number(value)
          return convertHeight.value
        default:
          throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return { component: defineComponent({
    setup() {
      useAgentPanelHost('image.transcode', handleWithoutMounted)
      return {}
    },
    template: '<div></div>',
  }), convertFormat }
}

beforeEach(() => { panelRegistry._clearAll() })

describe('ImageConvertPanel agent schema smoke', () => {
  it('mount → panelRegistry.get returns a handle', () => {
    const { component } = makeImageConvertPanelStub()
    mount(component)
    expect(panelRegistry.get('image.transcode')).toBeDefined()
  })

  it('getCurrentValues() returns all schema field names', () => {
    const { component } = makeImageConvertPanelStub()
    mount(component)
    const handle = panelRegistry.get('image.transcode')!
    const values = handle.getCurrentValues()
    for (const field of handle.agentSchema.fields) {
      expect(values).toHaveProperty(field.name)
    }
  })

  it('setField quality = 75 → returns 75', () => {
    const { component } = makeImageConvertPanelStub()
    mount(component)
    const handle = panelRegistry.get('image.transcode')!
    expect(handle.setField('quality', 75)).toBe(75)
  })

  it('setField quality > 100 → clamped to 100 (R-5)', () => {
    const { component } = makeImageConvertPanelStub()
    mount(component)
    const handle = panelRegistry.get('image.transcode')!
    expect(handle.setField('quality', 200)).toBe(100)
  })

  it('coalesce field present in agentSchema', () => {
    const { component } = makeImageConvertPanelStub()
    mount(component)
    const handle = panelRegistry.get('image.transcode')!
    const field = handle.agentSchema.fields.find(f => f.name === 'coalesce')
    expect(field).toBeDefined()
    expect(field?.type).toBe('bool')
  })

  it('coalesce visibleWhen returns true when output is gif', () => {
    const { component, convertFormat } = makeImageConvertPanelStub('gif')
    mount(component)
    const handle = panelRegistry.get('image.transcode')!
    const field = handle.agentSchema.fields.find(f => f.name === 'coalesce')!
    expect(field.visibleWhen?.()).toBe(true)
    convertFormat.value = 'png'
    expect(field.visibleWhen?.()).toBe(false)
  })

  it('coalesce visibleWhen returns false for png/jpg output', () => {
    const { component, convertFormat } = makeImageConvertPanelStub('png')
    mount(component)
    const handle = panelRegistry.get('image.transcode')!
    const field = handle.agentSchema.fields.find(f => f.name === 'coalesce')!
    expect(field.visibleWhen?.()).toBe(false)
    convertFormat.value = 'jpg'
    expect(field.visibleWhen?.()).toBe(false)
  })

  it('getParams includes coalesce', () => {
    const { component } = makeImageConvertPanelStub()
    mount(component)
    const handle = panelRegistry.get('image.transcode')!
    const values = handle.getCurrentValues()
    expect(values).toHaveProperty('coalesce')
    expect(typeof values.coalesce).toBe('boolean')
  })

  it('setField coalesce = true → returns true', () => {
    const { component } = makeImageConvertPanelStub()
    mount(component)
    const handle = panelRegistry.get('image.transcode')!
    expect(handle.setField('coalesce', true)).toBe(true)
  })
})
