import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import type { SelectItem } from '@/components/common/AppSelect.vue'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeDocumentOcrPanelStub(opts: {
  selectedModel?: string
  outputFormat?: 'md' | 'txt'
  modelOptions?: SelectItem[]
  isMultiSelect?: boolean
} = {}) {
  const selectedModel = ref(opts.selectedModel ?? 'qwen3vl:8b')
  const outputFormat  = ref<'md' | 'txt'>(opts.outputFormat ?? 'md')
  const modelOptions = ref<SelectItem[]>(opts.modelOptions ?? [
    { value: 'qwen3vl:8b', label: 'Qwen3-VL 8B' },
  ])
  const outputFormats = ref<{ value: string }[]>([{ value: 'md' }, { value: 'txt' }])

  const flattenOptions = (items: SelectItem[]) =>
    items.flatMap((o: SelectItem) =>
      'options' in o ? o.options.map(x => x.value) : [o.value]
    )

  const agentSchema = {
    panelId: 'document.ocr',
    fields: [
      { name: 'model',         type: 'enum' as const, options: () => flattenOptions(modelOptions.value) },
      { name: 'output_format', type: 'enum' as const, options: () => outputFormats.value.map(f => f.value) },
    ],
    actions: [],
    execute: { requiresConfirm: true, label: 'panel.doc_ocr.execute' },
  }

  const handle: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => opts.isMultiSelect ?? false,
    getCurrentValues: () => ({ model: selectedModel.value, output_format: outputFormat.value }),
    setField: (field, value) => {
      switch (field) {
        case 'model':         selectedModel.value = String(value);                  return selectedModel.value
        case 'output_format': outputFormat.value  = String(value) as 'md' | 'txt';  return outputFormat.value
        default: throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() { useAgentPanelHost('document.ocr', handle); return {} },
    template: '<div></div>',
  })
}

describe('DocumentOcrPanel agent integration', () => {
  beforeEach(() => { panelRegistry._clearAll() })

  it('registers handle on mount', () => {
    mount(makeDocumentOcrPanelStub())
    expect(panelRegistry.get('document.ocr')?.agentSchema.panelId).toBe('document.ocr')
  })

  it('exposes 2 fields', () => {
    mount(makeDocumentOcrPanelStub())
    const handle = panelRegistry.get('document.ocr')!
    expect(handle.agentSchema.fields.map(f => f.name)).toEqual(['model', 'output_format'])
  })

  it('execute schema: confirm=true, doc_ocr label', () => {
    mount(makeDocumentOcrPanelStub())
    const handle = panelRegistry.get('document.ocr')!
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.doc_ocr.execute' })
  })

  it('model options flatten SelectGroup entries (R1 C4 regression)', () => {
    const grouped = [
      { value: 'qwen3vl:8b', label: 'Qwen3-VL 8B' },
      { group: 'OpenAI', options: [{ value: 'gpt-4o', label: 'GPT-4o' }] },
    ] as SelectItem[]
    mount(makeDocumentOcrPanelStub({ modelOptions: grouped }))
    const handle = panelRegistry.get('document.ocr')!
    const f = handle.agentSchema.fields.find(f => f.name === 'model')!
    expect(f.options?.()).toEqual(['qwen3vl:8b', 'gpt-4o'])
  })

  it('output_format enum is md|txt', () => {
    mount(makeDocumentOcrPanelStub())
    const handle = panelRegistry.get('document.ocr')!
    const f = handle.agentSchema.fields.find(f => f.name === 'output_format')!
    expect(f.options?.()).toEqual(['md', 'txt'])
  })

  it('setField throws on unknown', () => {
    mount(makeDocumentOcrPanelStub())
    const handle = panelRegistry.get('document.ocr')!
    expect(() => handle.setField('bogus', 'x')).toThrow('Unknown field: bogus')
  })

  it('getCurrentValues reflects state', () => {
    mount(makeDocumentOcrPanelStub({ outputFormat: 'txt' }))
    const handle = panelRegistry.get('document.ocr')!
    expect(handle.getCurrentValues()).toEqual({ model: 'qwen3vl:8b', output_format: 'txt' })
  })

  it('unmount removes handle', () => {
    const wrapper = mount(makeDocumentOcrPanelStub())
    expect(panelRegistry.get('document.ocr')).toBeTruthy()
    wrapper.unmount()
    expect(panelRegistry.get('document.ocr')).toBeUndefined()
  })

  it('isMultiSelect=true → reports multi', () => {
    mount(makeDocumentOcrPanelStub({ isMultiSelect: true }))
    const handle = panelRegistry.get('document.ocr')!
    expect(handle.isMultiSelect()).toBe(true)
  })
})
