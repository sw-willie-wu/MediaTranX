/**
 * Smoke test — ImageCompressPanel agent schema
 *
 * Verifies:
 *   - After mount, panelRegistry.get('image.compress') returns a handle
 *   - agentSchema.panelId === 'image.compress'
 *   - getCurrentValues() returns all schema field names
 *   - strength field is present
 *   - GIF advanced fields (gif_colors, gif_frame_drop, gif_optimize_transparency) are present
 *   - visibleWhen gates on gif input (false when non-GIF, true when GIF)
 *   - PNG advanced field (png_mode) is present
 *   - visibleWhen for png_mode gates on PNG input (true for PNG, false for GIF)
 *   - setField clamping works
 */

import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeImageCompressPanelStub(gifInput = false, pngInput = false, jpegInput = false, webpInput = false) {
  const strength = ref(75)
  const gifColors = ref(128)
  const gifFrameDrop = ref(0)
  const gifOptimizeTransparency = ref(true)
  const pngMode = ref<'lossy' | 'lossless'>('lossy')
  const jpegProgressive = ref(true)
  const jpegKeepMetadata = ref(false)
  const webpLossless = ref(false)
  const isGif = ref(gifInput)
  const isPng = ref(pngInput)
  const isJpeg = ref(jpegInput)
  const isWebp = ref(webpInput)

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
      { name: 'png_mode', type: 'enum' as const,
        options: () => ['lossy', 'lossless'],
        visibleWhen: () => isPng.value },
      { name: 'jpeg_progressive', type: 'bool' as const,
        visibleWhen: () => isJpeg.value },
      { name: 'jpeg_keep_metadata', type: 'bool' as const,
        visibleWhen: () => isJpeg.value },
      { name: 'webp_lossless', type: 'bool' as const,
        visibleWhen: () => isWebp.value },
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
      png_mode: pngMode.value,
      jpeg_progressive: jpegProgressive.value,
      jpeg_keep_metadata: jpegKeepMetadata.value,
      webp_lossless: webpLossless.value,
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
        case 'png_mode':
          pngMode.value = value === 'lossless' ? 'lossless' : 'lossy'
          return pngMode.value
        case 'jpeg_progressive':
          jpegProgressive.value = Boolean(value)
          return jpegProgressive.value
        case 'jpeg_keep_metadata':
          jpegKeepMetadata.value = Boolean(value)
          return jpegKeepMetadata.value
        case 'webp_lossless':
          webpLossless.value = Boolean(value)
          return webpLossless.value
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

  return { component, isGif, isPng, isJpeg, isWebp }
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
    const gifFieldNames = ['gif_colors', 'gif_frame_drop', 'gif_optimize_transparency']
    for (const name of gifFieldNames) {
      expect(handle.agentSchema.fields.find(f => f.name === name), `${name} should be in schema`).toBeDefined()
    }
  })

  it('visibleWhen for GIF fields returns false when input is not GIF', () => {
    const { component } = makeImageCompressPanelStub(false)
    mount(component)
    const handle = panelRegistry.get('image.compress')!
    const gifFields = handle.agentSchema.fields.filter(f => f.name.startsWith('gif_'))
    for (const field of gifFields) {
      expect(field.visibleWhen?.(), `${field.name} visibleWhen should be false for non-GIF`).toBe(false)
    }
  })

  it('visibleWhen for GIF fields returns true when input is GIF', () => {
    const { component, isGif } = makeImageCompressPanelStub(false)
    mount(component)
    isGif.value = true
    const handle = panelRegistry.get('image.compress')!
    const gifFields = handle.agentSchema.fields.filter(f => f.name.startsWith('gif_'))
    for (const field of gifFields) {
      expect(field.visibleWhen?.(), `${field.name} visibleWhen should be true for GIF`).toBe(true)
    }
  })

  it('png_mode field present in schema', () => {
    const { component } = makeImageCompressPanelStub()
    mount(component)
    const handle = panelRegistry.get('image.compress')!
    const pngField = handle.agentSchema.fields.find(f => f.name === 'png_mode')
    expect(pngField).toBeDefined()
    expect(pngField?.type).toBe('enum')
  })

  it('visibleWhen for png_mode returns true when input is PNG', () => {
    const { component, isPng } = makeImageCompressPanelStub(false, false)
    mount(component)
    isPng.value = true
    const handle = panelRegistry.get('image.compress')!
    const pngField = handle.agentSchema.fields.find(f => f.name === 'png_mode')!
    expect(pngField.visibleWhen?.()).toBe(true)
  })

  it('visibleWhen for png_mode returns false when input is GIF', () => {
    const { component } = makeImageCompressPanelStub(true, false)
    mount(component)
    const handle = panelRegistry.get('image.compress')!
    const pngField = handle.agentSchema.fields.find(f => f.name === 'png_mode')!
    expect(pngField.visibleWhen?.()).toBe(false)
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

  it('JPEG advanced fields present in schema', () => {
    const { component } = makeImageCompressPanelStub()
    mount(component)
    const handle = panelRegistry.get('image.compress')!
    const jpegFieldNames = ['jpeg_progressive', 'jpeg_keep_metadata']
    for (const name of jpegFieldNames) {
      expect(handle.agentSchema.fields.find(f => f.name === name), `${name} should be in schema`).toBeDefined()
    }
  })

  it('visibleWhen for jpeg fields returns false when input is not JPEG', () => {
    const { component } = makeImageCompressPanelStub(false, false, false)
    mount(component)
    const handle = panelRegistry.get('image.compress')!
    const jpegFields = handle.agentSchema.fields.filter(f => f.name.startsWith('jpeg_'))
    for (const field of jpegFields) {
      expect(field.visibleWhen?.(), `${field.name} visibleWhen should be false for non-JPEG`).toBe(false)
    }
  })

  it('visibleWhen for jpeg fields returns true when input is JPEG', () => {
    const { component, isJpeg } = makeImageCompressPanelStub(false, false, false)
    mount(component)
    isJpeg.value = true
    const handle = panelRegistry.get('image.compress')!
    const jpegFields = handle.agentSchema.fields.filter(f => f.name.startsWith('jpeg_'))
    for (const field of jpegFields) {
      expect(field.visibleWhen?.(), `${field.name} visibleWhen should be true for JPEG`).toBe(true)
    }
  })

  it('webp_lossless field present in schema', () => {
    const { component } = makeImageCompressPanelStub()
    mount(component)
    const handle = panelRegistry.get('image.compress')!
    const webpField = handle.agentSchema.fields.find(f => f.name === 'webp_lossless')
    expect(webpField).toBeDefined()
    expect(webpField?.type).toBe('bool')
  })

  it('visibleWhen for webp_lossless returns false when input is not WebP', () => {
    const { component } = makeImageCompressPanelStub(false, false, false, false)
    mount(component)
    const handle = panelRegistry.get('image.compress')!
    const webpField = handle.agentSchema.fields.find(f => f.name === 'webp_lossless')!
    expect(webpField.visibleWhen?.()).toBe(false)
  })

  it('visibleWhen for webp_lossless returns true when input is WebP', () => {
    const { component, isWebp } = makeImageCompressPanelStub(false, false, false, false)
    mount(component)
    isWebp.value = true
    const handle = panelRegistry.get('image.compress')!
    const webpField = handle.agentSchema.fields.find(f => f.name === 'webp_lossless')!
    expect(webpField.visibleWhen?.()).toBe(true)
  })
})
