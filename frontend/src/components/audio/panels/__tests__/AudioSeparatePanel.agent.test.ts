import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeAudioSeparatePanelStub(opts: {
  outputFormat?: string
  generateMidi?: boolean
  stemVocals?: boolean; stemDrums?: boolean; stemBass?: boolean
  stemGuitar?: boolean; stemPiano?: boolean; stemOther?: boolean
  isMultiSelect?: boolean
} = {}) {
  const outputFormat  = ref(opts.outputFormat  ?? 'wav')
  const generateMidi  = ref(opts.generateMidi  ?? false)
  const stemVocals    = ref(opts.stemVocals    ?? true)
  const stemDrums     = ref(opts.stemDrums     ?? true)
  const stemBass      = ref(opts.stemBass      ?? true)
  const stemGuitar    = ref(opts.stemGuitar    ?? true)
  const stemPiano     = ref(opts.stemPiano     ?? true)
  const stemOther     = ref(opts.stemOther     ?? true)
  const outputFormats = ref<{ value: string }[]>([{ value: 'wav' }, { value: 'flac' }, { value: 'mp3' }])

  const agentSchema = {
    panelId: 'audio.separate',
    fields: [
      { name: 'output_format', type: 'enum' as const, options: () => outputFormats.value.map(f => f.value) },
      { name: 'generate_midi', type: 'bool' as const },
      { name: 'stem_vocals',   type: 'bool' as const },
      { name: 'stem_drums',    type: 'bool' as const },
      { name: 'stem_bass',     type: 'bool' as const },
      { name: 'stem_guitar',   type: 'bool' as const },
      { name: 'stem_piano',    type: 'bool' as const },
      { name: 'stem_other',    type: 'bool' as const },
    ],
    actions: [],
    execute: { requiresConfirm: true, label: 'panel.separate.execute' },
  }

  const handle: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => opts.isMultiSelect ?? false,
    getCurrentValues: () => ({
      output_format: outputFormat.value, generate_midi: generateMidi.value,
      stem_vocals: stemVocals.value, stem_drums: stemDrums.value, stem_bass: stemBass.value,
      stem_guitar: stemGuitar.value, stem_piano: stemPiano.value, stem_other: stemOther.value,
    }),
    setField: (field, value) => {
      switch (field) {
        case 'output_format': outputFormat.value = String(value);  return outputFormat.value
        case 'generate_midi': generateMidi.value = Boolean(value); return generateMidi.value
        case 'stem_vocals':   stemVocals.value   = Boolean(value); return stemVocals.value
        case 'stem_drums':    stemDrums.value    = Boolean(value); return stemDrums.value
        case 'stem_bass':     stemBass.value     = Boolean(value); return stemBass.value
        case 'stem_guitar':   stemGuitar.value   = Boolean(value); return stemGuitar.value
        case 'stem_piano':    stemPiano.value    = Boolean(value); return stemPiano.value
        case 'stem_other':    stemOther.value    = Boolean(value); return stemOther.value
        default: throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() { useAgentPanelHost('audio.separate', handle); return {} },
    template: '<div></div>',
  })
}

describe('AudioSeparatePanel agent integration', () => {
  beforeEach(() => { panelRegistry._clearAll() })

  it('registers handle on mount', () => {
    mount(makeAudioSeparatePanelStub())
    expect(panelRegistry.get('audio.separate')?.agentSchema.panelId).toBe('audio.separate')
  })

  it('exposes exactly 8 fields (no model)', () => {
    mount(makeAudioSeparatePanelStub())
    const handle = panelRegistry.get('audio.separate')!
    expect(handle.agentSchema.fields).toHaveLength(8)
    expect(handle.agentSchema.fields.map(f => f.name)).toEqual([
      'output_format', 'generate_midi',
      'stem_vocals', 'stem_drums', 'stem_bass', 'stem_guitar', 'stem_piano', 'stem_other',
    ])
  })

  it('execute schema: confirm=true, separate label', () => {
    mount(makeAudioSeparatePanelStub())
    const handle = panelRegistry.get('audio.separate')!
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.separate.execute' })
  })

  it('output_format enum lists wav/flac/mp3', () => {
    mount(makeAudioSeparatePanelStub())
    const handle = panelRegistry.get('audio.separate')!
    const f = handle.agentSchema.fields.find(f => f.name === 'output_format')!
    expect(f.options?.()).toEqual(['wav', 'flac', 'mp3'])
  })

  it('toggles stem flags independently', () => {
    mount(makeAudioSeparatePanelStub())
    const handle = panelRegistry.get('audio.separate')!
    handle.setField('stem_vocals', false)
    handle.setField('stem_drums', false)
    expect(handle.getCurrentValues().stem_vocals).toBe(false)
    expect(handle.getCurrentValues().stem_drums).toBe(false)
    expect(handle.getCurrentValues().stem_bass).toBe(true)
  })

  it('all stems coerce to boolean', () => {
    mount(makeAudioSeparatePanelStub())
    const handle = panelRegistry.get('audio.separate')!
    expect(handle.setField('stem_guitar', 'truthy')).toBe(true)
    expect(handle.setField('stem_guitar', 0)).toBe(false)
    expect(handle.setField('stem_piano', 1)).toBe(true)
  })

  it('generate_midi coerces to boolean', () => {
    mount(makeAudioSeparatePanelStub())
    const handle = panelRegistry.get('audio.separate')!
    expect(handle.setField('generate_midi', 'yes')).toBe(true)
    expect(handle.setField('generate_midi', 0)).toBe(false)
  })

  it('setField throws on unknown', () => {
    mount(makeAudioSeparatePanelStub())
    const handle = panelRegistry.get('audio.separate')!
    expect(() => handle.setField('bogus', 'x')).toThrow('Unknown field: bogus')
  })

  it('getCurrentValues reflects all 8 fields', () => {
    mount(makeAudioSeparatePanelStub({ outputFormat: 'flac', generateMidi: true, stemVocals: false }))
    const handle = panelRegistry.get('audio.separate')!
    const v = handle.getCurrentValues()
    expect(v.output_format).toBe('flac')
    expect(v.generate_midi).toBe(true)
    expect(v.stem_vocals).toBe(false)
    expect(v.stem_drums).toBe(true)
  })

  it('unmount removes handle', () => {
    const wrapper = mount(makeAudioSeparatePanelStub())
    expect(panelRegistry.get('audio.separate')).toBeTruthy()
    wrapper.unmount()
    expect(panelRegistry.get('audio.separate')).toBeUndefined()
  })

  it('isMultiSelect=true → reports multi', () => {
    mount(makeAudioSeparatePanelStub({ isMultiSelect: true }))
    const handle = panelRegistry.get('audio.separate')!
    expect(handle.isMultiSelect()).toBe(true)
  })
})
