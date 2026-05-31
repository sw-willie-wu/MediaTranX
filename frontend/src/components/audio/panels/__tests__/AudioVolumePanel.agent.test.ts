import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeAudioVolumePanelStub(opts: {
  mode?: 'adjust' | 'normalize'
  volumeDb?: number
  isMultiSelect?: boolean
} = {}) {
  const mode     = ref<'adjust' | 'normalize'>(opts.mode ?? 'adjust')
  const volumeDb = ref(opts.volumeDb ?? 0)

  const agentSchema = {
    panelId: 'audio.volume',
    fields: [
      { name: 'mode',      type: 'enum'   as const, options: () => ['adjust', 'normalize'] },
      { name: 'volume_db', type: 'number' as const, min: -20, max: 20, step: 1,
        visibleWhen: () => mode.value === 'adjust' },
    ],
    actions: [],
    execute: { requiresConfirm: false, label: 'panel.volume.execute' },
  }

  const handle: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => opts.isMultiSelect ?? false,
    getCurrentValues: () => ({ mode: mode.value, volume_db: volumeDb.value }),
    setField: (field, value) => {
      const clamp = (v: unknown, lo: number, hi: number) => Math.min(Math.max(Number(v), lo), hi)
      switch (field) {
        case 'mode':      mode.value = String(value) as 'adjust' | 'normalize'; return mode.value
        case 'volume_db': { const c = clamp(value, -20, 20); volumeDb.value = c; return c }
        default: throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() { useAgentPanelHost('audio.volume', handle); return {} },
    template: '<div></div>',
  })
}

describe('AudioVolumePanel agent integration', () => {
  beforeEach(() => { panelRegistry._clearAll() })

  it('registers handle on mount', () => {
    mount(makeAudioVolumePanelStub())
    expect(panelRegistry.get('audio.volume')?.agentSchema.panelId).toBe('audio.volume')
  })

  it('exposes 2 fields: mode + volume_db', () => {
    mount(makeAudioVolumePanelStub())
    const handle = panelRegistry.get('audio.volume')!
    expect(handle.agentSchema.fields.map(f => f.name)).toEqual(['mode', 'volume_db'])
  })

  it('mode enum is adjust|normalize', () => {
    mount(makeAudioVolumePanelStub())
    const handle = panelRegistry.get('audio.volume')!
    const f = handle.agentSchema.fields.find(f => f.name === 'mode')!
    expect(f.options?.()).toEqual(['adjust', 'normalize'])
  })

  it('execute schema: confirm=false, volume label', () => {
    mount(makeAudioVolumePanelStub())
    const handle = panelRegistry.get('audio.volume')!
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: false, label: 'panel.volume.execute' })
  })

  it('volume_db clamps to -20..20', () => {
    mount(makeAudioVolumePanelStub())
    const handle = panelRegistry.get('audio.volume')!
    expect(handle.setField('volume_db', 100)).toBe(20)
    expect(handle.setField('volume_db', -100)).toBe(-20)
    expect(handle.setField('volume_db', 5)).toBe(5)
    expect(handle.setField('volume_db', -10)).toBe(-10)
  })

  it('volume_db visibleWhen=adjust only', () => {
    mount(makeAudioVolumePanelStub({ mode: 'adjust' }))
    const handle = panelRegistry.get('audio.volume')!
    const f = handle.agentSchema.fields.find(f => f.name === 'volume_db')!
    expect(f.visibleWhen?.()).toBe(true)
    handle.setField('mode', 'normalize')
    expect(f.visibleWhen?.()).toBe(false)
  })

  it('setField mode updates state', () => {
    mount(makeAudioVolumePanelStub())
    const handle = panelRegistry.get('audio.volume')!
    expect(handle.setField('mode', 'normalize')).toBe('normalize')
    expect(handle.getCurrentValues().mode).toBe('normalize')
  })

  it('setField throws on unknown', () => {
    mount(makeAudioVolumePanelStub())
    const handle = panelRegistry.get('audio.volume')!
    expect(() => handle.setField('bogus', 'x')).toThrow('Unknown field: bogus')
  })

  it('getCurrentValues reflects state', () => {
    mount(makeAudioVolumePanelStub({ mode: 'normalize', volumeDb: -5 }))
    const handle = panelRegistry.get('audio.volume')!
    expect(handle.getCurrentValues()).toEqual({ mode: 'normalize', volume_db: -5 })
  })

  it('unmount removes handle', () => {
    const wrapper = mount(makeAudioVolumePanelStub())
    expect(panelRegistry.get('audio.volume')).toBeTruthy()
    wrapper.unmount()
    expect(panelRegistry.get('audio.volume')).toBeUndefined()
  })

  it('isMultiSelect=true → reports multi', () => {
    mount(makeAudioVolumePanelStub({ isMultiSelect: true }))
    const handle = panelRegistry.get('audio.volume')!
    expect(handle.isMultiSelect()).toBe(true)
  })
})
