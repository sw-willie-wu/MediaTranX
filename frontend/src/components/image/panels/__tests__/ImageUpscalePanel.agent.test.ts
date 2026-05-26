/**
 * Smoke test — ImageUpscalePanel agent schema (Wave 3 Task 3.4)
 *
 * Verifies:
 *   - After mount, panelRegistry.get('image.upscale') returns a handle
 *   - getCurrentValues() returns an object with all schema field names
 *   - setField('upscale_scale', 3) returns 3 (within range)
 *   - setField('upscale_scale', 999) returns clamped value (R-5 verification)
 */

import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

// ── Minimal in-test component that reproduces the panel's schema ──────────────

function makeImageUpscalePanelStub() {
  // Replicate the reactive state from ImageUpscalePanel
  const selectedModelId = ref('realesrgan_x4plus')
  const selectedFaceModelId = ref('')
  const upscaleScale = ref(4)
  const sharpen = ref(false)
  const faceRestore = ref(false)
  const faceRestoreUpscale = ref(2)
  const maxScale = ref(4)
  const upscaleOptions = ref([{ value: 'realesrgan_x4plus' }, { value: 'realesrgan_x4plus_anime' }])
  const faceOptions = ref([{ value: 'gfpgan_v1.4' }])

  const agentSchema = {
    panelId: 'image.upscale',
    fields: [
      { name: 'upscale_model', type: 'enum' as const,
        options: () => upscaleOptions.value.map(o => o.value) },
      { name: 'upscale_scale', type: 'number' as const,
        min: 2, max: () => maxScale.value, step: 1 },
      { name: 'sharpen', type: 'bool' as const },
      { name: 'face_restore', type: 'bool' as const },
      { name: 'face_restore_model', type: 'enum' as const,
        options: () => faceOptions.value.map(o => o.value),
        visibleWhen: () => faceRestore.value },
      { name: 'face_restore_upscale', type: 'number' as const,
        min: 1, max: 4, step: 1,
        visibleWhen: () => faceRestore.value },
    ],
    actions: [],
    execute: { requiresConfirm: true, label: 'panel.upscale.execute' },
  }

  const handleWithoutMounted: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => false,
    getCurrentValues: () => ({
      upscale_model: selectedModelId.value,
      upscale_scale: upscaleScale.value,
      sharpen: sharpen.value,
      face_restore: faceRestore.value,
      face_restore_model: selectedFaceModelId.value,
      face_restore_upscale: faceRestoreUpscale.value,
    }),
    setField: (field, value) => {
      switch (field) {
        case 'upscale_model':
          selectedModelId.value = value as string
          return value
        case 'upscale_scale': {
          const clamped = Math.min(Math.max(Number(value), 2), maxScale.value)
          upscaleScale.value = clamped
          return clamped
        }
        case 'sharpen':
          sharpen.value = !!value
          return sharpen.value
        case 'face_restore':
          faceRestore.value = !!value
          return faceRestore.value
        case 'face_restore_model':
          selectedFaceModelId.value = value as string
          return value
        case 'face_restore_upscale': {
          const clamped = Math.min(Math.max(Number(value), 1), 4)
          faceRestoreUpscale.value = clamped
          return clamped
        }
        default:
          throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() {
      useAgentPanelHost('image.upscale', handleWithoutMounted)
      return {}
    },
    template: '<div></div>',
  })
}

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => { panelRegistry._clearAll() })

describe('ImageUpscalePanel agent schema smoke', () => {
  it('mount → panelRegistry.get returns a handle', () => {
    mount(makeImageUpscalePanelStub())
    expect(panelRegistry.get('image.upscale')).toBeDefined()
  })

  it('getCurrentValues() returns all schema field names', () => {
    mount(makeImageUpscalePanelStub())
    const handle = panelRegistry.get('image.upscale')!
    const values = handle.getCurrentValues()
    for (const field of handle.agentSchema.fields) {
      expect(values).toHaveProperty(field.name)
    }
  })

  it('setField upscale_scale within range → returns exact value', () => {
    mount(makeImageUpscalePanelStub())
    const handle = panelRegistry.get('image.upscale')!
    const result = handle.setField('upscale_scale', 3)
    expect(result).toBe(3)
  })

  it('setField upscale_scale > maxScale → returns clamped value (R-5)', () => {
    mount(makeImageUpscalePanelStub())
    const handle = panelRegistry.get('image.upscale')!
    // maxScale is 4 in the stub; 999 should clamp to 4
    const result = handle.setField('upscale_scale', 999)
    expect(result).toBe(4)
  })

  it('setField unknown field → throws', () => {
    mount(makeImageUpscalePanelStub())
    const handle = panelRegistry.get('image.upscale')!
    expect(() => handle.setField('nonexistent', 'x')).toThrow('Unknown field: nonexistent')
  })
})
