import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeVideoInterpolatePanelStub(opts: {
  model?: string
  mode?: string
  targetFps?: number
  outputFormat?: string
  videoCodec?: string
  isMultiSelect?: boolean
} = {}) {
  const model        = ref(opts.model        ?? 'v4.26')
  const mode         = ref(opts.mode         ?? '2x')
  const targetFps    = ref(opts.targetFps    ?? 60)
  const outputFormat = ref(opts.outputFormat ?? 'mp4')
  const videoCodec   = ref(opts.videoCodec   ?? 'h264')
  const modelOptions  = ref<{ value: string }[]>([{ value: 'v4.26' }, { value: 'v4.25' }])
  const modeOptions   = ref<{ value: string }[]>([{ value: '2x' }, { value: '4x' }, { value: 'custom' }])
  const formatOptions = ref<{ value: string }[]>([{ value: 'mp4' }, { value: 'mkv' }])
  const codecOptions  = ref<{ value: string }[]>([{ value: 'h264' }, { value: 'h265' }])

  const agentSchema = {
    panelId: 'video.interpolate',
    fields: [
      { name: 'model',         type: 'enum'   as const, options: () => modelOptions.value.map(o => o.value) },
      { name: 'mode',          type: 'enum'   as const, options: () => modeOptions.value.map(m => m.value) },
      { name: 'target_fps',    type: 'number' as const, min: 2, max: 240, step: 1,
        visibleWhen: () => mode.value === 'custom' },
      { name: 'output_format', type: 'enum'   as const, options: () => formatOptions.value.map(f => f.value) },
      { name: 'video_codec',   type: 'enum'   as const, options: () => codecOptions.value.map(c => c.value) },
    ],
    actions: [],
    execute: { requiresConfirm: true, label: 'panel.interpolate.execute' },
  }

  const handle: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => opts.isMultiSelect ?? false,
    getCurrentValues: () => ({
      model: model.value, mode: mode.value, target_fps: targetFps.value,
      output_format: outputFormat.value, video_codec: videoCodec.value,
    }),
    setField: (field, value) => {
      const clamp = (v: unknown, lo: number, hi: number) => Math.min(Math.max(Number(v), lo), hi)
      switch (field) {
        case 'model':         model.value        = String(value);                  return model.value
        case 'mode':          mode.value         = String(value);                  return mode.value
        case 'target_fps':    { const c = clamp(value, 2, 240); targetFps.value = c; return c }
        case 'output_format': outputFormat.value = String(value);                  return outputFormat.value
        case 'video_codec':   videoCodec.value   = String(value);                  return videoCodec.value
        default: throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() {
      useAgentPanelHost('video.interpolate', handle)
      return {}
    },
    template: '<div></div>',
  })
}

describe('VideoInterpolatePanel agent integration', () => {
  beforeEach(() => { panelRegistry._clearAll() })

  it('registers handle on mount', () => {
    mount(makeVideoInterpolatePanelStub())
    expect(panelRegistry.get('video.interpolate')?.agentSchema.panelId).toBe('video.interpolate')
  })

  it('exposes correct field list (5 fields)', () => {
    mount(makeVideoInterpolatePanelStub())
    const handle = panelRegistry.get('video.interpolate')!
    expect(handle.agentSchema.fields.map(f => f.name)).toEqual([
      'model', 'mode', 'target_fps', 'output_format', 'video_codec',
    ])
  })

  it('mode enum includes 3 options (2x, 4x, custom)', () => {
    mount(makeVideoInterpolatePanelStub())
    const handle = panelRegistry.get('video.interpolate')!
    const f = handle.agentSchema.fields.find(f => f.name === 'mode')!
    expect(f.options?.()).toEqual(['2x', '4x', 'custom'])
  })

  it('target_fps clamps to 2..240', () => {
    mount(makeVideoInterpolatePanelStub())
    const handle = panelRegistry.get('video.interpolate')!
    expect(handle.setField('target_fps', 500)).toBe(240)
    expect(handle.setField('target_fps', 0)).toBe(2)
    expect(handle.setField('target_fps', 60)).toBe(60)
  })

  it('target_fps visibleWhen reacts to mode change', () => {
    mount(makeVideoInterpolatePanelStub({ mode: '2x' }))
    const handle = panelRegistry.get('video.interpolate')!
    const fpsField = handle.agentSchema.fields.find(f => f.name === 'target_fps')!
    expect(fpsField.visibleWhen?.()).toBe(false)
    handle.setField('mode', 'custom')
    expect(fpsField.visibleWhen?.()).toBe(true)
    handle.setField('mode', '4x')
    expect(fpsField.visibleWhen?.()).toBe(false)
  })

  it('execute schema is confirm=true with interpolate label', () => {
    mount(makeVideoInterpolatePanelStub())
    const handle = panelRegistry.get('video.interpolate')!
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.interpolate.execute' })
  })

  it('setField throws on unknown field', () => {
    mount(makeVideoInterpolatePanelStub())
    const handle = panelRegistry.get('video.interpolate')!
    expect(() => handle.setField('bogus', 'x')).toThrow('Unknown field: bogus')
  })

  it('getCurrentValues reflects state', () => {
    mount(makeVideoInterpolatePanelStub({ model: 'v4.25', mode: 'custom', targetFps: 120, outputFormat: 'mkv', videoCodec: 'h265' }))
    const handle = panelRegistry.get('video.interpolate')!
    expect(handle.getCurrentValues()).toEqual({
      model: 'v4.25', mode: 'custom', target_fps: 120, output_format: 'mkv', video_codec: 'h265',
    })
  })

  it('unmount removes handle from registry', () => {
    const wrapper = mount(makeVideoInterpolatePanelStub())
    expect(panelRegistry.get('video.interpolate')).toBeTruthy()
    wrapper.unmount()
    expect(panelRegistry.get('video.interpolate')).toBeUndefined()
  })

  it('isMultiSelect=true → handle reports multi', () => {
    mount(makeVideoInterpolatePanelStub({ isMultiSelect: true }))
    const handle = panelRegistry.get('video.interpolate')!
    expect(handle.isMultiSelect()).toBe(true)
  })
})
