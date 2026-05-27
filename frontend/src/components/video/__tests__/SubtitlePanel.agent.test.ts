/**
 * Smoke test — SubtitlePanel agent schema (Wave 3 Task 3.4)
 *
 * Verifies:
 *   - After mount, panelRegistry.get('video.subtitle') returns a handle
 *   - getCurrentValues() returns an object with all schema field names
 *   - setField('vocal_separation', true) returns true
 *   - isMultiSelect() always returns false (m16 — subtitle panel hardcodes false)
 */

import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeSubtitlePanelStub() {
  const language = ref('')
  const modelSize = ref('medium')
  const vocalSeparation = ref(false)
  const outputFormat = ref('srt')

  const languages = ref([{ value: '' }, { value: 'en' }, { value: 'zh' }])
  const modelSizesWithBadge = ref([{ value: 'tiny' }, { value: 'medium' }, { value: 'large-v3' }])
  const outputFormats = ref([{ value: 'srt' }, { value: 'vtt' }])

  const agentSchema = {
    panelId: 'video.subtitle',
    fields: [
      { name: 'language', type: 'enum' as const,
        options: () => languages.value.map(l => l.value) },
      { name: 'model_size', type: 'enum' as const,
        options: () => modelSizesWithBadge.value.map(m => m.value) },
      { name: 'vocal_separation', type: 'bool' as const },
      { name: 'output_format', type: 'enum' as const,
        options: () => outputFormats.value.map(f => f.value) },
    ],
    actions: [],
    execute: { requiresConfirm: true, label: 'panel.subtitle.execute' },
  }

  const handleWithoutMounted: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => false,  // subtitle does not support multi-select (m16)
    getCurrentValues: () => ({
      language: language.value,
      model_size: modelSize.value,
      vocal_separation: vocalSeparation.value,
      output_format: outputFormat.value,
    }),
    setField: (field, value) => {
      switch (field) {
        case 'language':
          language.value = value as string
          return value
        case 'model_size':
          modelSize.value = value as string
          return value
        case 'vocal_separation':
          vocalSeparation.value = !!value
          return vocalSeparation.value
        case 'output_format':
          outputFormat.value = value as string
          return value
        default:
          throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() {
      useAgentPanelHost('video.subtitle', handleWithoutMounted)
      return {}
    },
    template: '<div></div>',
  })
}

beforeEach(() => { panelRegistry._clearAll() })

describe('SubtitlePanel agent schema smoke', () => {
  it('mount → panelRegistry.get returns a handle', () => {
    mount(makeSubtitlePanelStub())
    expect(panelRegistry.get('video.subtitle')).toBeDefined()
  })

  it('getCurrentValues() returns all schema field names', () => {
    mount(makeSubtitlePanelStub())
    const handle = panelRegistry.get('video.subtitle')!
    const values = handle.getCurrentValues()
    for (const field of handle.agentSchema.fields) {
      expect(values).toHaveProperty(field.name)
    }
  })

  it('setField vocal_separation = true → returns true', () => {
    mount(makeSubtitlePanelStub())
    const handle = panelRegistry.get('video.subtitle')!
    expect(handle.setField('vocal_separation', true)).toBe(true)
  })

  it('isMultiSelect() returns false (m16 — subtitle panel hardcodes false)', () => {
    mount(makeSubtitlePanelStub())
    const handle = panelRegistry.get('video.subtitle')!
    expect(handle.isMultiSelect()).toBe(false)
  })
})
