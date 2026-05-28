import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import type { SelectItem } from '@/components/common/AppSelect.vue'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeVideoSummaryPanelStub(opts: {
  whisperModelSize?: string
  llmModel?: string
  vlmModel?: string
  summaryMode?: string
  vocalSeparation?: boolean
  llmOptions?: SelectItem[]
  vlmOptions?: SelectItem[]
  isMultiSelect?: boolean
} = {}) {
  const whisperModelSize = ref(opts.whisperModelSize ?? 'medium')
  const llmModel         = ref(opts.llmModel         ?? 'qwen3.5:9b')
  const vlmModel         = ref(opts.vlmModel         ?? '')
  const summaryMode      = ref(opts.summaryMode      ?? 'bullets')
  const vocalSeparation  = ref(opts.vocalSeparation  ?? false)
  const whisperModelOptions = ref<{ value: string }[]>([{ value: 'medium' }, { value: 'large-v3' }])
  const llmOptions = ref<SelectItem[]>(opts.llmOptions ?? [
    { value: 'qwen3.5:9b', label: 'Qwen3.5 9B' },
  ])
  const vlmOptions = ref<SelectItem[]>(opts.vlmOptions ?? [
    { value: '',           label: 'No VLM' },
    { value: 'qwen3vl:8b', label: 'Qwen3-VL 8B' },
  ])
  const summaryModeOptions = ref<{ value: string }[]>([{ value: 'bullets' }, { value: 'narrative' }])

  const flattenOptions = (items: SelectItem[]) =>
    items.flatMap((o: SelectItem) =>
      'options' in o ? o.options.map(x => x.value) : [o.value]
    )

  const agentSchema = {
    panelId: 'video.summary',
    fields: [
      { name: 'whisper_model',    type: 'enum' as const, options: () => whisperModelOptions.value.map(m => m.value) },
      { name: 'llm_model',        type: 'enum' as const, options: () => flattenOptions(llmOptions.value) },
      { name: 'vlm_model',        type: 'enum' as const, options: () => flattenOptions(vlmOptions.value) },
      { name: 'summary_mode',     type: 'enum' as const, options: () => summaryModeOptions.value.map(o => o.value) },
      { name: 'vocal_separation', type: 'bool' as const },
    ],
    actions: [],
    execute: { requiresConfirm: true, label: 'panel.summary.execute' },
  }

  const handle: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => opts.isMultiSelect ?? false,
    getCurrentValues: () => ({
      whisper_model:    whisperModelSize.value,
      llm_model:        llmModel.value,
      vlm_model:        vlmModel.value,
      summary_mode:     summaryMode.value,
      vocal_separation: vocalSeparation.value,
    }),
    setField: (field, value) => {
      switch (field) {
        case 'whisper_model':    whisperModelSize.value = String(value); return whisperModelSize.value
        case 'llm_model':        llmModel.value         = String(value); return llmModel.value
        case 'vlm_model':        vlmModel.value         = String(value); return vlmModel.value
        case 'summary_mode':     summaryMode.value      = String(value); return summaryMode.value
        case 'vocal_separation': vocalSeparation.value  = Boolean(value); return vocalSeparation.value
        default: throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() {
      useAgentPanelHost('video.summary', handle)
      return {}
    },
    template: '<div></div>',
  })
}

describe('VideoSummaryPanel agent integration', () => {
  beforeEach(() => { panelRegistry._clearAll() })

  it('registers handle on mount', () => {
    mount(makeVideoSummaryPanelStub())
    expect(panelRegistry.get('video.summary')?.agentSchema.panelId).toBe('video.summary')
  })

  it('exposes 5 fields in correct order', () => {
    mount(makeVideoSummaryPanelStub())
    const handle = panelRegistry.get('video.summary')!
    expect(handle.agentSchema.fields.map(f => f.name)).toEqual([
      'whisper_model', 'llm_model', 'vlm_model', 'summary_mode', 'vocal_separation',
    ])
  })

  it('execute schema: confirm=true, summary label', () => {
    mount(makeVideoSummaryPanelStub())
    const handle = panelRegistry.get('video.summary')!
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.summary.execute' })
  })

  it('vlm_model accepts empty-string sentinel for "no VLM"', () => {
    mount(makeVideoSummaryPanelStub())
    const handle = panelRegistry.get('video.summary')!
    expect(handle.setField('vlm_model', '')).toBe('')
    expect(handle.getCurrentValues().vlm_model).toBe('')
  })

  it('vlm_model options include "" sentinel and concrete models', () => {
    mount(makeVideoSummaryPanelStub())
    const handle = panelRegistry.get('video.summary')!
    const f = handle.agentSchema.fields.find(f => f.name === 'vlm_model')!
    const opts = f.options?.() ?? []
    expect(opts).toContain('')
    expect(opts).toContain('qwen3vl:8b')
  })

  it('llm_model flattens grouped options (local + cloud)', () => {
    const grouped: SelectItem[] = [
      { value: 'qwen3.5:9b', label: 'Qwen3.5 9B' },
      { group: 'OpenAI', options: [{ value: 'gpt-4o-mini', label: 'GPT-4o Mini' }] },
    ] as SelectItem[]
    mount(makeVideoSummaryPanelStub({ llmOptions: grouped }))
    const handle = panelRegistry.get('video.summary')!
    const f = handle.agentSchema.fields.find(f => f.name === 'llm_model')!
    expect(f.options?.()).toEqual(['qwen3.5:9b', 'gpt-4o-mini'])
  })

  it('summary_mode enum is bullets|narrative', () => {
    mount(makeVideoSummaryPanelStub())
    const handle = panelRegistry.get('video.summary')!
    const f = handle.agentSchema.fields.find(f => f.name === 'summary_mode')!
    expect(f.options?.()).toEqual(['bullets', 'narrative'])
  })

  it('vocal_separation coerces to boolean', () => {
    mount(makeVideoSummaryPanelStub())
    const handle = panelRegistry.get('video.summary')!
    expect(handle.setField('vocal_separation', 'true')).toBe(true)
    expect(handle.setField('vocal_separation', 0)).toBe(false)
  })

  it('setField throws on unknown field', () => {
    mount(makeVideoSummaryPanelStub())
    const handle = panelRegistry.get('video.summary')!
    expect(() => handle.setField('bogus', 'x')).toThrow('Unknown field: bogus')
  })

  it('getCurrentValues reflects state', () => {
    mount(makeVideoSummaryPanelStub({
      whisperModelSize: 'large-v3', llmModel: 'qwen3:8b:Q4_K_M',
      vlmModel: 'qwen3vl:8b', summaryMode: 'narrative', vocalSeparation: true,
    }))
    const handle = panelRegistry.get('video.summary')!
    expect(handle.getCurrentValues()).toEqual({
      whisper_model: 'large-v3', llm_model: 'qwen3:8b:Q4_K_M',
      vlm_model: 'qwen3vl:8b', summary_mode: 'narrative', vocal_separation: true,
    })
  })

  it('unmount removes handle from registry', () => {
    const wrapper = mount(makeVideoSummaryPanelStub())
    expect(panelRegistry.get('video.summary')).toBeTruthy()
    wrapper.unmount()
    expect(panelRegistry.get('video.summary')).toBeUndefined()
  })

  it('isMultiSelect=true → handle reports multi', () => {
    mount(makeVideoSummaryPanelStub({ isMultiSelect: true }))
    const handle = panelRegistry.get('video.summary')!
    expect(handle.isMultiSelect()).toBe(true)
  })
})
