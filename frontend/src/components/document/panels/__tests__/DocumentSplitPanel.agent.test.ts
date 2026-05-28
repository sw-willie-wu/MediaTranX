import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeDocumentSplitPanelStub(opts: {
  pages?: string
  isMultiSelect?: boolean
} = {}) {
  const pages = ref(opts.pages ?? '')

  const agentSchema = {
    panelId: 'document.split',
    fields: [
      { name: 'pages', type: 'string' as const },
    ],
    actions: [],
    execute: { requiresConfirm: false, label: 'panel.doc_split.execute' },
  }

  const handle: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => opts.isMultiSelect ?? false,
    getCurrentValues: () => ({ pages: pages.value }),
    setField: (field, value) => {
      switch (field) {
        case 'pages': pages.value = String(value); return pages.value
        default: throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() { useAgentPanelHost('document.split', handle); return {} },
    template: '<div></div>',
  })
}

describe('DocumentSplitPanel agent integration', () => {
  beforeEach(() => { panelRegistry._clearAll() })

  it('registers handle on mount', () => {
    mount(makeDocumentSplitPanelStub())
    expect(panelRegistry.get('document.split')?.agentSchema.panelId).toBe('document.split')
  })

  it('exposes 1 field (pages)', () => {
    mount(makeDocumentSplitPanelStub())
    const handle = panelRegistry.get('document.split')!
    expect(handle.agentSchema.fields.map(f => f.name)).toEqual(['pages'])
  })

  it('execute schema: confirm=false, doc_split label', () => {
    mount(makeDocumentSplitPanelStub())
    const handle = panelRegistry.get('document.split')!
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: false, label: 'panel.doc_split.execute' })
  })

  it('setField pages updates', () => {
    mount(makeDocumentSplitPanelStub())
    const handle = panelRegistry.get('document.split')!
    expect(handle.setField('pages', '1-3')).toBe('1-3')
    expect(handle.getCurrentValues().pages).toBe('1-3')
  })

  it('setField pages accepts free-form range string', () => {
    mount(makeDocumentSplitPanelStub())
    const handle = panelRegistry.get('document.split')!
    expect(handle.setField('pages', '1-3, 5, 7-9')).toBe('1-3, 5, 7-9')
    expect(handle.getCurrentValues().pages).toBe('1-3, 5, 7-9')
  })

  it('setField throws on unknown', () => {
    mount(makeDocumentSplitPanelStub())
    const handle = panelRegistry.get('document.split')!
    expect(() => handle.setField('bogus', 'x')).toThrow('Unknown field: bogus')
  })

  it('unmount removes handle', () => {
    const wrapper = mount(makeDocumentSplitPanelStub())
    expect(panelRegistry.get('document.split')).toBeTruthy()
    wrapper.unmount()
    expect(panelRegistry.get('document.split')).toBeUndefined()
  })

  it('isMultiSelect=true → reports multi', () => {
    mount(makeDocumentSplitPanelStub({ isMultiSelect: true }))
    const handle = panelRegistry.get('document.split')!
    expect(handle.isMultiSelect()).toBe(true)
  })
})
