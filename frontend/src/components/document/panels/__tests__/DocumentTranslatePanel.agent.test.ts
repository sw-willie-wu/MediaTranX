import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import type { SelectItem } from '@/components/common/AppSelect.vue'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeDocumentTranslatePanelStub(opts: {
  selectedTranslateModel?: string
  sourceLanguage?: string
  targetLanguage?: string
  translateStyle?: string
  translateModelOptions?: SelectItem[]
  isMultiSelect?: boolean
} = {}) {
  const selectedTranslateModel = ref(opts.selectedTranslateModel ?? 'qwen3:8b:Q4_K_M')
  const sourceLanguage         = ref(opts.sourceLanguage         ?? 'en')
  const targetLanguage         = ref(opts.targetLanguage         ?? 'zh-TW')
  const translateStyle         = ref(opts.translateStyle         ?? 'colloquial')
  const translateModelOptions = ref<SelectItem[]>(opts.translateModelOptions ?? [
    { value: 'qwen3:8b:Q4_K_M', label: 'Qwen3 8B Q4' },
  ])
  const languageOptions = ref<{ value: string }[]>([{ value: 'en' }, { value: 'zh-TW' }, { value: 'ja' }])
  const translateStyles = ref<{ value: string }[]>([{ value: 'colloquial' }, { value: 'formal' }])

  const flattenOptions = (items: SelectItem[]) =>
    items.flatMap((o: SelectItem) =>
      'options' in o ? (o as unknown as { options: { value: string }[] }).options.map(x => x.value) : [o.value]
    )

  const agentSchema = {
    panelId: 'document.translate',
    fields: [
      { name: 'model',           type: 'enum' as const, options: () => flattenOptions(translateModelOptions.value) },
      { name: 'source_language', type: 'enum' as const, options: () => languageOptions.value.map(l => l.value) },
      { name: 'target_language', type: 'enum' as const, options: () => languageOptions.value.map(l => l.value) },
      { name: 'translate_style', type: 'enum' as const, options: () => translateStyles.value.map(s => s.value) },
    ],
    actions: [],
    execute: { requiresConfirm: true, label: 'panel.doc_translate.execute' },
  }

  const handle: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => opts.isMultiSelect ?? false,
    getCurrentValues: () => ({
      model: selectedTranslateModel.value,
      source_language: sourceLanguage.value,
      target_language: targetLanguage.value,
      translate_style: translateStyle.value,
    }),
    setField: (field, value) => {
      switch (field) {
        case 'model':           selectedTranslateModel.value = String(value); return selectedTranslateModel.value
        case 'source_language': sourceLanguage.value         = String(value); return sourceLanguage.value
        case 'target_language': targetLanguage.value         = String(value); return targetLanguage.value
        case 'translate_style': translateStyle.value         = String(value); return translateStyle.value
        default: throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() { useAgentPanelHost('document.translate', handle); return {} },
    template: '<div></div>',
  })
}

describe('DocumentTranslatePanel agent integration', () => {
  beforeEach(() => { panelRegistry._clearAll() })

  it('registers handle on mount', () => {
    mount(makeDocumentTranslatePanelStub())
    expect(panelRegistry.get('document.translate')?.agentSchema.panelId).toBe('document.translate')
  })

  it('exposes 4 fields in order', () => {
    mount(makeDocumentTranslatePanelStub())
    const handle = panelRegistry.get('document.translate')!
    expect(handle.agentSchema.fields.map(f => f.name)).toEqual([
      'model', 'source_language', 'target_language', 'translate_style',
    ])
  })

  it('source and target languages share same option set', () => {
    mount(makeDocumentTranslatePanelStub())
    const handle = panelRegistry.get('document.translate')!
    const src = handle.agentSchema.fields.find(f => f.name === 'source_language')!
    const tgt = handle.agentSchema.fields.find(f => f.name === 'target_language')!
    expect(src.options?.()).toEqual(tgt.options?.())
  })

  it('glossary field NOT exposed', () => {
    mount(makeDocumentTranslatePanelStub())
    const handle = panelRegistry.get('document.translate')!
    const names = handle.agentSchema.fields.map(f => f.name)
    expect(names).not.toContain('glossary')
    expect(names).not.toContain('glossary_text')
    expect(names).not.toContain('glossaryText')
  })

  it('execute schema: confirm=true, doc_translate label', () => {
    mount(makeDocumentTranslatePanelStub())
    const handle = panelRegistry.get('document.translate')!
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.doc_translate.execute' })
  })

  it('model flattens grouped options (local + cloud)', () => {
    const grouped = [
      { value: 'qwen3:8b:Q4_K_M', label: 'Qwen3 8B' },
      { group: 'OpenAI', options: [{ value: 'gpt-4o', label: 'GPT-4o' }] },
    ] as SelectItem[]
    mount(makeDocumentTranslatePanelStub({ translateModelOptions: grouped }))
    const handle = panelRegistry.get('document.translate')!
    const f = handle.agentSchema.fields.find(f => f.name === 'model')!
    expect(f.options?.()).toEqual(['qwen3:8b:Q4_K_M', 'gpt-4o'])
  })

  it('setField throws on unknown', () => {
    mount(makeDocumentTranslatePanelStub())
    const handle = panelRegistry.get('document.translate')!
    expect(() => handle.setField('bogus', 'x')).toThrow('Unknown field: bogus')
  })

  it('getCurrentValues reflects state', () => {
    mount(makeDocumentTranslatePanelStub({ targetLanguage: 'ja', translateStyle: 'formal' }))
    const handle = panelRegistry.get('document.translate')!
    expect(handle.getCurrentValues()).toEqual({
      model: 'qwen3:8b:Q4_K_M', source_language: 'en', target_language: 'ja', translate_style: 'formal',
    })
  })

  it('unmount removes handle', () => {
    const wrapper = mount(makeDocumentTranslatePanelStub())
    expect(panelRegistry.get('document.translate')).toBeTruthy()
    wrapper.unmount()
    expect(panelRegistry.get('document.translate')).toBeUndefined()
  })

  it('isMultiSelect=true → reports multi', () => {
    mount(makeDocumentTranslatePanelStub({ isMultiSelect: true }))
    const handle = panelRegistry.get('document.translate')!
    expect(handle.isMultiSelect()).toBe(true)
  })
})
