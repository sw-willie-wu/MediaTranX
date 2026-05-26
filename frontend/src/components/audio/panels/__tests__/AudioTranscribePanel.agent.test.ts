/**
 * Smoke test — AudioTranscribePanel agent schema (Wave 3 Task 3.4)
 *
 * Verifies:
 *   - After mount, panelRegistry.get('audio.transcribe') returns a handle
 *   - getCurrentValues() returns an object with all schema field names
 *   - setField('translate', true) returns true
 *   - setField('model_size', 'large-v3') returns 'large-v3'
 */

import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeAudioTranscribePanelStub() {
  const modelSize = ref('medium')
  const language = ref('')
  const outputFormat = ref('txt')
  const vocalSeparation = ref(false)
  const alignEnabled = ref(false)
  const translateEnabled = ref(false)
  const targetLanguage = ref('zh-TW')
  const summarizeEnabled = ref(false)

  const modelSizes = ref([{ value: 'tiny' }, { value: 'medium' }, { value: 'large-v3' }])
  const languages = ref([{ value: '' }, { value: 'en' }, { value: 'zh' }])
  const outputFormats = ref([{ value: 'txt' }, { value: 'srt' }])
  const translateLanguages = ref([{ value: 'zh-TW' }, { value: 'zh-CN' }, { value: 'en' }])

  const agentSchema = {
    panelId: 'audio.transcribe',
    fields: [
      { name: 'model_size', type: 'enum' as const,
        options: () => modelSizes.value.map(m => m.value) },
      { name: 'language', type: 'enum' as const,
        options: () => languages.value.map(l => l.value) },
      { name: 'output_format', type: 'enum' as const,
        options: () => outputFormats.value.map(f => f.value) },
      { name: 'vocal_separation', type: 'bool' as const },
      { name: 'align', type: 'bool' as const },
      { name: 'translate', type: 'bool' as const },
      { name: 'target_language', type: 'enum' as const,
        options: () => translateLanguages.value.map(l => l.value),
        visibleWhen: () => translateEnabled.value },
      { name: 'summarize', type: 'bool' as const },
    ],
    actions: [],
    execute: { requiresConfirm: true, label: 'panel.transcribe.execute' },
  }

  const handleWithoutMounted: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => false,
    getCurrentValues: () => ({
      model_size: modelSize.value,
      language: language.value,
      output_format: outputFormat.value,
      vocal_separation: vocalSeparation.value,
      align: alignEnabled.value,
      translate: translateEnabled.value,
      target_language: targetLanguage.value,
      summarize: summarizeEnabled.value,
    }),
    setField: (field, value) => {
      switch (field) {
        case 'model_size':
          modelSize.value = value as string
          return value
        case 'language':
          language.value = value as string
          return value
        case 'output_format':
          outputFormat.value = value as string
          return value
        case 'vocal_separation':
          vocalSeparation.value = !!value
          return vocalSeparation.value
        case 'align':
          alignEnabled.value = !!value
          return alignEnabled.value
        case 'translate':
          translateEnabled.value = !!value
          return translateEnabled.value
        case 'target_language':
          targetLanguage.value = value as string
          return value
        case 'summarize':
          summarizeEnabled.value = !!value
          return summarizeEnabled.value
        default:
          throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() {
      useAgentPanelHost('audio.transcribe', handleWithoutMounted)
      return {}
    },
    template: '<div></div>',
  })
}

beforeEach(() => { panelRegistry._clearAll() })

describe('AudioTranscribePanel agent schema smoke', () => {
  it('mount → panelRegistry.get returns a handle', () => {
    mount(makeAudioTranscribePanelStub())
    expect(panelRegistry.get('audio.transcribe')).toBeDefined()
  })

  it('getCurrentValues() returns all schema field names', () => {
    mount(makeAudioTranscribePanelStub())
    const handle = panelRegistry.get('audio.transcribe')!
    const values = handle.getCurrentValues()
    for (const field of handle.agentSchema.fields) {
      expect(values).toHaveProperty(field.name)
    }
  })

  it('setField translate = true → returns true', () => {
    mount(makeAudioTranscribePanelStub())
    const handle = panelRegistry.get('audio.transcribe')!
    expect(handle.setField('translate', true)).toBe(true)
  })

  it('setField model_size = large-v3 → returns large-v3', () => {
    mount(makeAudioTranscribePanelStub())
    const handle = panelRegistry.get('audio.transcribe')!
    expect(handle.setField('model_size', 'large-v3')).toBe('large-v3')
  })
})
