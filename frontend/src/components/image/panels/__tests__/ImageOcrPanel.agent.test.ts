/**
 * Smoke test — ImageOcrPanel agent schema (Phase 2.A Task 2.6)
 *
 * Stub pattern + M1 flatten regression for SelectGroup options.
 */
import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'
import type { SelectItem, SelectOption, SelectGroup } from '@/components/common/AppSelect.vue'

function makeImageOcrPanelStub(opts: {
  modelOptions?: SelectItem[]
  isMultiSelect?: boolean
} = {}) {
  const selectedModel = ref('qwen3vl:8b')
  const outputFormat = ref<'md' | 'txt'>('md')
  const modelOptions = ref<SelectItem[]>(opts.modelOptions ?? [
    { value: 'qwen3vl:8b', label: 'Qwen3-VL 8B' } as SelectOption,
  ])

  const agentSchema = {
    panelId: 'image.ocr',
    fields: [
      { name: 'model', type: 'enum' as const,
        options: () => modelOptions.value.flatMap((o: SelectItem) =>
          'options' in o ? o.options.map(x => x.value) : [o.value]
        ),
      },
      { name: 'output_format', type: 'enum' as const, options: () => ['md', 'txt'] },
    ],
    actions: [],
    execute: { requiresConfirm: true, label: 'panel.ocr.execute' },
  }

  const handle: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => opts.isMultiSelect ?? false,
    getCurrentValues: () => ({ model: selectedModel.value, output_format: outputFormat.value }),
    setField: (field, value) => {
      switch (field) {
        case 'model': selectedModel.value = value as string; return selectedModel.value
        case 'output_format': outputFormat.value = value as 'md' | 'txt'; return outputFormat.value
        default: throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() {
      useAgentPanelHost('image.ocr', handle)
      return {}
    },
    template: '<div></div>',
  })
}

describe('ImageOcrPanel agent integration', () => {
  beforeEach(() => { panelRegistry._clearAll() })

  it('registers handle on mount', () => {
    mount(makeImageOcrPanelStub())
    expect(panelRegistry.get('image.ocr')?.agentSchema.panelId).toBe('image.ocr')
  })

  it('agentSchema fields list contains [model, output_format]', () => {
    mount(makeImageOcrPanelStub())
    const handle = panelRegistry.get('image.ocr')!
    expect(handle.agentSchema.fields.map(f => f.name)).toEqual(['model', 'output_format'])
    expect(handle.agentSchema.fields.every(f => f.type === 'enum')).toBe(true)
  })

  it('output_format options returns ["md", "txt"]', () => {
    mount(makeImageOcrPanelStub())
    const handle = panelRegistry.get('image.ocr')!
    const outputFormatField = handle.agentSchema.fields.find(f => f.name === 'output_format')!
    expect(outputFormatField.options!()).toEqual(['md', 'txt'])
  })

  it('model options returns flat string[] when modelOptions is local-only SelectOption[]', () => {
    const localOnly: SelectItem[] = [
      { value: 'qwen3vl:8b', label: 'Qwen3-VL 8B' } as SelectOption,
      { value: 'qwen3vl:32b', label: 'Qwen3-VL 32B' } as SelectOption,
    ]
    mount(makeImageOcrPanelStub({ modelOptions: localOnly }))
    const handle = panelRegistry.get('image.ocr')!
    const modelField = handle.agentSchema.fields.find(f => f.name === 'model')!
    const opts = modelField.options!()
    expect(Array.isArray(opts)).toBe(true)
    expect(opts.every(o => typeof o === 'string')).toBe(true)
    expect(opts).toEqual(['qwen3vl:8b', 'qwen3vl:32b'])
  })

  // M1 critical regression — SelectGroup entries must be flattened
  it('model options flatten SelectGroup entries (M1 regression)', () => {
    const grouped: SelectItem[] = [
      { value: 'qwen3vl:8b', label: 'Qwen3-VL 8B' } as SelectOption,
      {
        group: 'OpenAI',
        options: [{ value: 'remote:openai:1:gpt-4o', label: 'GPT-4o' }],
      } as SelectGroup,
    ]
    mount(makeImageOcrPanelStub({ modelOptions: grouped }))
    const handle = panelRegistry.get('image.ocr')!
    const modelField = handle.agentSchema.fields.find(f => f.name === 'model')!
    const opts = modelField.options!()
    expect(Array.isArray(opts)).toBe(true)
    expect(opts.every(o => typeof o === 'string')).toBe(true)
    expect(opts).toContain('qwen3vl:8b')
    expect(opts).toContain('remote:openai:1:gpt-4o')
    expect(opts.length).toBe(2)
    // No undefined entries — would fail OpenAI strict mode schema validation
    expect(opts.some(o => o === undefined)).toBe(false)
  })

  it('setField model with family:size form', () => {
    mount(makeImageOcrPanelStub())
    const handle = panelRegistry.get('image.ocr')!
    expect(handle.setField('model', 'qwen3vl:8b')).toBe('qwen3vl:8b')
    expect(handle.getCurrentValues().model).toBe('qwen3vl:8b')
  })

  it('setField model with remote:provider:connId:modelId form (no parsing)', () => {
    mount(makeImageOcrPanelStub())
    const handle = panelRegistry.get('image.ocr')!
    expect(handle.setField('model', 'remote:openai:1:gpt-4o')).toBe('remote:openai:1:gpt-4o')
    expect(handle.getCurrentValues().model).toBe('remote:openai:1:gpt-4o')
  })

  it('setField output_format with md or txt', () => {
    mount(makeImageOcrPanelStub())
    const handle = panelRegistry.get('image.ocr')!
    expect(handle.setField('output_format', 'txt')).toBe('txt')
    expect(handle.getCurrentValues().output_format).toBe('txt')
  })

  it('setField throws on unknown field NAME', () => {
    mount(makeImageOcrPanelStub())
    const handle = panelRegistry.get('image.ocr')!
    expect(() => handle.setField('nonexistent', 'x')).toThrow(/Unknown field/)
  })

  it('getCurrentValues default {model: "qwen3vl:8b", output_format: "md"}', () => {
    mount(makeImageOcrPanelStub())
    expect(panelRegistry.get('image.ocr')!.getCurrentValues()).toEqual({
      model: 'qwen3vl:8b', output_format: 'md',
    })
  })

  it('execute requiresConfirm is true (GPU VLM or cloud billing)', () => {
    mount(makeImageOcrPanelStub())
    expect(panelRegistry.get('image.ocr')!.agentSchema.execute!.requiresConfirm).toBe(true)
  })

  it('no actions declared', () => {
    mount(makeImageOcrPanelStub())
    expect(panelRegistry.get('image.ocr')!.agentSchema.actions).toEqual([])
  })

  it('isMultiSelect honors prop + unregisters on unmount', () => {
    const w = mount(makeImageOcrPanelStub({ isMultiSelect: true }))
    expect(panelRegistry.get('image.ocr')!.isMultiSelect()).toBe(true)
    w.unmount()
    expect(panelRegistry.get('image.ocr')).toBeUndefined()
  })
})
