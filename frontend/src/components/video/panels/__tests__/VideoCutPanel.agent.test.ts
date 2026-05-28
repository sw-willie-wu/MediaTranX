import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeVideoCutPanelStub(opts: {
  startTime?: string
  endTime?: string
  streamCopy?: boolean
  isMultiSelect?: boolean
} = {}) {
  const startTime  = ref(opts.startTime  ?? '00:00:00')
  const endTime    = ref(opts.endTime    ?? '00:00:10')
  const streamCopy = ref(opts.streamCopy ?? false)

  const agentSchema = {
    panelId: 'video.cut',
    fields: [
      { name: 'start_time',  type: 'string' as const },
      { name: 'end_time',    type: 'string' as const },
      { name: 'stream_copy', type: 'bool'   as const },
    ],
    actions: [],
    execute: { requiresConfirm: true, label: 'panel.cut.execute' },
  }

  const handle: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => opts.isMultiSelect ?? false,
    getCurrentValues: () => ({
      start_time:  startTime.value,
      end_time:    endTime.value,
      stream_copy: streamCopy.value,
    }),
    setField: (field, value) => {
      switch (field) {
        case 'start_time':  startTime.value  = String(value);   return startTime.value
        case 'end_time':    endTime.value    = String(value);   return endTime.value
        case 'stream_copy': streamCopy.value = Boolean(value);  return streamCopy.value
        default: throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() {
      useAgentPanelHost('video.cut', handle)
      return {}
    },
    template: '<div></div>',
  })
}

describe('VideoCutPanel agent integration', () => {
  beforeEach(() => { panelRegistry._clearAll() })

  it('registers handle on mount', () => {
    mount(makeVideoCutPanelStub())
    expect(panelRegistry.get('video.cut')?.agentSchema.panelId).toBe('video.cut')
  })

  it('exposes correct field list', () => {
    mount(makeVideoCutPanelStub())
    const handle = panelRegistry.get('video.cut')!
    expect(handle.agentSchema.fields.map(f => f.name)).toEqual(['start_time', 'end_time', 'stream_copy'])
  })

  it('execute schema is confirm=true with cut label', () => {
    mount(makeVideoCutPanelStub())
    const handle = panelRegistry.get('video.cut')!
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.cut.execute' })
  })

  it('setField start_time updates state', () => {
    mount(makeVideoCutPanelStub())
    const handle = panelRegistry.get('video.cut')!
    expect(handle.setField('start_time', '00:00:05')).toBe('00:00:05')
    expect(handle.getCurrentValues().start_time).toBe('00:00:05')
  })

  it('setField stream_copy coerces to boolean', () => {
    mount(makeVideoCutPanelStub())
    const handle = panelRegistry.get('video.cut')!
    expect(handle.setField('stream_copy', 'truthy')).toBe(true)
    expect(handle.setField('stream_copy', 0)).toBe(false)
  })

  it('setField throws on unknown field', () => {
    mount(makeVideoCutPanelStub())
    const handle = panelRegistry.get('video.cut')!
    expect(() => handle.setField('bogus', 'x')).toThrow('Unknown field: bogus')
  })

  it('getCurrentValues reflects state', () => {
    mount(makeVideoCutPanelStub({ startTime: '00:00:01', endTime: '00:01:00' }))
    const handle = panelRegistry.get('video.cut')!
    expect(handle.getCurrentValues()).toEqual({
      start_time:  '00:00:01',
      end_time:    '00:01:00',
      stream_copy: false,
    })
  })

  it('unmount removes handle from registry', () => {
    const wrapper = mount(makeVideoCutPanelStub())
    expect(panelRegistry.get('video.cut')).toBeTruthy()
    wrapper.unmount()
    expect(panelRegistry.get('video.cut')).toBeUndefined()
  })

  it('isMultiSelect=true → handle reports multi', () => {
    mount(makeVideoCutPanelStub({ isMultiSelect: true }))
    const handle = panelRegistry.get('video.cut')!
    expect(handle.isMultiSelect()).toBe(true)
  })
})
