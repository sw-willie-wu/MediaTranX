import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeVideoEnhancePanelStub(opts: {
  variant?: string
  outputFormat?: string
  videoCodec?: string
  isMultiSelect?: boolean
} = {}) {
  const variant      = ref(opts.variant      ?? 'x4plus')
  const outputFormat = ref(opts.outputFormat ?? 'mp4')
  const videoCodec   = ref(opts.videoCodec   ?? 'h264')
  const variantOptions = ref<{ value: string }[]>([{ value: 'x4plus' }, { value: 'x2plus' }])
  const formatOptions  = ref<{ value: string }[]>([{ value: 'mp4' }, { value: 'mkv' }])
  const codecOptions   = ref<{ value: string }[]>([{ value: 'h264' }, { value: 'h265' }])

  const agentSchema = {
    panelId: 'video.enhance',
    fields: [
      { name: 'model',         type: 'enum' as const, options: () => variantOptions.value.map(o => o.value) },
      { name: 'output_format', type: 'enum' as const, options: () => formatOptions.value.map(f => f.value) },
      { name: 'video_codec',   type: 'enum' as const, options: () => codecOptions.value.map(c => c.value) },
    ],
    actions: [],
    execute: { requiresConfirm: true, label: 'panel.enhance.execute' },
  }

  const handle: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => opts.isMultiSelect ?? false,
    getCurrentValues: () => ({
      model:         variant.value,
      output_format: outputFormat.value,
      video_codec:   videoCodec.value,
    }),
    setField: (field, value) => {
      switch (field) {
        case 'model':         variant.value      = String(value); return variant.value
        case 'output_format': outputFormat.value = String(value); return outputFormat.value
        case 'video_codec':   videoCodec.value   = String(value); return videoCodec.value
        default: throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() {
      useAgentPanelHost('video.enhance', handle)
      return {}
    },
    template: '<div></div>',
  })
}

describe('VideoEnhancePanel agent integration', () => {
  beforeEach(() => { panelRegistry._clearAll() })

  it('registers handle on mount', () => {
    mount(makeVideoEnhancePanelStub())
    expect(panelRegistry.get('video.enhance')?.agentSchema.panelId).toBe('video.enhance')
  })

  it('exposes correct field list (3 enums)', () => {
    mount(makeVideoEnhancePanelStub())
    const handle = panelRegistry.get('video.enhance')!
    expect(handle.agentSchema.fields.map(f => f.name)).toEqual(['model', 'output_format', 'video_codec'])
    expect(handle.agentSchema.fields.every(f => f.type === 'enum')).toBe(true)
  })

  it('execute schema is confirm=true with enhance label', () => {
    mount(makeVideoEnhancePanelStub())
    const handle = panelRegistry.get('video.enhance')!
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.enhance.execute' })
  })

  it('setField model updates state', () => {
    mount(makeVideoEnhancePanelStub())
    const handle = panelRegistry.get('video.enhance')!
    expect(handle.setField('model', 'x2plus')).toBe('x2plus')
    expect(handle.getCurrentValues().model).toBe('x2plus')
  })

  it('setField video_codec updates state', () => {
    mount(makeVideoEnhancePanelStub())
    const handle = panelRegistry.get('video.enhance')!
    expect(handle.setField('video_codec', 'h265')).toBe('h265')
  })

  it('setField throws on unknown field', () => {
    mount(makeVideoEnhancePanelStub())
    const handle = panelRegistry.get('video.enhance')!
    expect(() => handle.setField('bogus', 'x')).toThrow('Unknown field: bogus')
  })

  it('getCurrentValues reflects state', () => {
    mount(makeVideoEnhancePanelStub({ variant: 'x2plus', outputFormat: 'mkv', videoCodec: 'h265' }))
    const handle = panelRegistry.get('video.enhance')!
    expect(handle.getCurrentValues()).toEqual({ model: 'x2plus', output_format: 'mkv', video_codec: 'h265' })
  })

  it('unmount removes handle from registry', () => {
    const wrapper = mount(makeVideoEnhancePanelStub())
    expect(panelRegistry.get('video.enhance')).toBeTruthy()
    wrapper.unmount()
    expect(panelRegistry.get('video.enhance')).toBeUndefined()
  })

  it('isMultiSelect=true → handle reports multi', () => {
    mount(makeVideoEnhancePanelStub({ isMultiSelect: true }))
    const handle = panelRegistry.get('video.enhance')!
    expect(handle.isMultiSelect()).toBe(true)
  })

  it('model enum options come from variantOptions', () => {
    mount(makeVideoEnhancePanelStub())
    const handle = panelRegistry.get('video.enhance')!
    const f = handle.agentSchema.fields.find(f => f.name === 'model')!
    expect(f.options?.()).toEqual(['x4plus', 'x2plus'])
  })
})
