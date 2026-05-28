import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeAudioTranscodePanelStub(opts: {
  outputFormat?: string
  bitrate?: string
  sampleRate?: string
  showBitrate?: boolean
  isMultiSelect?: boolean
} = {}) {
  // CRITICAL: formats is non-reactive top-level const, grouped shape
  const formats = [
    { group: 'Lossy',    options: [{ value: 'mp3', label: 'MP3' }, { value: 'aac', label: 'AAC' }] },
    { group: 'Lossless', options: [{ value: 'flac', label: 'FLAC' }, { value: 'wav', label: 'WAV' }] },
  ]
  const outputFormat = ref(opts.outputFormat ?? 'mp3')
  const bitrate      = ref(opts.bitrate      ?? '192k')
  const sampleRate   = ref(opts.sampleRate   ?? '')
  const showBitrate  = ref(opts.showBitrate  ?? true)
  const bitrates     = ref<{ value: string }[]>([{ value: '' }, { value: '128k' }, { value: '192k' }, { value: '320k' }])
  const sampleRates  = ref<{ value: string }[]>([{ value: '' }, { value: '44100' }, { value: '48000' }])

  const agentSchema = {
    panelId: 'audio.transcode',
    fields: [
      { name: 'output_format', type: 'enum' as const,
        options: () => formats.flatMap(g => g.options.map(o => o.value)) },
      { name: 'bitrate', type: 'enum' as const,
        options: () => bitrates.value.map(b => b.value),
        visibleWhen: () => showBitrate.value },
      { name: 'sample_rate', type: 'enum' as const,
        options: () => sampleRates.value.map(r => r.value) },
    ],
    actions: [],
    execute: { requiresConfirm: true, label: 'panel.audio_transcode.execute' },
  }

  const handle: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => opts.isMultiSelect ?? false,
    getCurrentValues: () => ({
      output_format: outputFormat.value, bitrate: bitrate.value, sample_rate: sampleRate.value,
    }),
    setField: (field, value) => {
      switch (field) {
        case 'output_format': outputFormat.value = String(value); return outputFormat.value
        case 'bitrate':       bitrate.value      = String(value); return bitrate.value
        case 'sample_rate':   sampleRate.value   = String(value); return sampleRate.value
        default: throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() { useAgentPanelHost('audio.transcode', handle); return {} },
    template: '<div></div>',
  })
}

describe('AudioTranscodePanel agent integration', () => {
  beforeEach(() => { panelRegistry._clearAll() })

  it('registers handle on mount', () => {
    mount(makeAudioTranscodePanelStub())
    expect(panelRegistry.get('audio.transcode')?.agentSchema.panelId).toBe('audio.transcode')
  })

  it('exposes 3 fields in order', () => {
    mount(makeAudioTranscodePanelStub())
    const handle = panelRegistry.get('audio.transcode')!
    expect(handle.agentSchema.fields.map(f => f.name)).toEqual(['output_format', 'bitrate', 'sample_rate'])
  })

  it('execute schema: confirm=true, audio_transcode label', () => {
    mount(makeAudioTranscodePanelStub())
    const handle = panelRegistry.get('audio.transcode')!
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.audio_transcode.execute' })
  })

  it('output_format options flatten grouped formats (lossy + lossless)', () => {
    mount(makeAudioTranscodePanelStub())
    const handle = panelRegistry.get('audio.transcode')!
    const f = handle.agentSchema.fields.find(f => f.name === 'output_format')!
    expect(f.options?.()).toEqual(['mp3', 'aac', 'flac', 'wav'])
  })

  it('bitrate visibleWhen hides for lossless (showBitrate=false)', () => {
    mount(makeAudioTranscodePanelStub({ showBitrate: false }))
    const handle = panelRegistry.get('audio.transcode')!
    const f = handle.agentSchema.fields.find(f => f.name === 'bitrate')!
    expect(f.visibleWhen?.()).toBe(false)
  })

  it('bitrate visibleWhen shows for lossy (showBitrate=true)', () => {
    mount(makeAudioTranscodePanelStub({ showBitrate: true }))
    const handle = panelRegistry.get('audio.transcode')!
    const f = handle.agentSchema.fields.find(f => f.name === 'bitrate')!
    expect(f.visibleWhen?.()).toBe(true)
  })

  it('bitrate accepts "" sentinel for "keep original"', () => {
    mount(makeAudioTranscodePanelStub())
    const handle = panelRegistry.get('audio.transcode')!
    expect(handle.setField('bitrate', '')).toBe('')
    expect(handle.getCurrentValues().bitrate).toBe('')
  })

  it('sample_rate accepts "" sentinel', () => {
    mount(makeAudioTranscodePanelStub())
    const handle = panelRegistry.get('audio.transcode')!
    expect(handle.setField('sample_rate', '')).toBe('')
  })

  it('setField throws on unknown', () => {
    mount(makeAudioTranscodePanelStub())
    const handle = panelRegistry.get('audio.transcode')!
    expect(() => handle.setField('bogus', 'x')).toThrow('Unknown field: bogus')
  })

  it('getCurrentValues reflects state', () => {
    mount(makeAudioTranscodePanelStub({ outputFormat: 'flac', bitrate: '', sampleRate: '48000' }))
    const handle = panelRegistry.get('audio.transcode')!
    expect(handle.getCurrentValues()).toEqual({ output_format: 'flac', bitrate: '', sample_rate: '48000' })
  })

  it('unmount removes handle', () => {
    const wrapper = mount(makeAudioTranscodePanelStub())
    expect(panelRegistry.get('audio.transcode')).toBeTruthy()
    wrapper.unmount()
    expect(panelRegistry.get('audio.transcode')).toBeUndefined()
  })

  it('isMultiSelect=true → reports multi', () => {
    mount(makeAudioTranscodePanelStub({ isMultiSelect: true }))
    const handle = panelRegistry.get('audio.transcode')!
    expect(handle.isMultiSelect()).toBe(true)
  })
})
