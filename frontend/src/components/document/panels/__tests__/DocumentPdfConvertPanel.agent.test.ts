import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeDocumentPdfConvertPanelStub(opts: {
  outputFormat?: string
  isMultiSelect?: boolean
} = {}) {
  const outputFormat = ref(opts.outputFormat ?? 'txt')
  const outputFormatOptions = ref<{ value: string }[]>([{ value: 'txt' }, { value: 'md' }, { value: 'images' }])

  const agentSchema = {
    panelId: 'document.pdf_convert',
    fields: [
      { name: 'output_format', type: 'enum' as const, options: () => outputFormatOptions.value.map(f => f.value) },
    ],
    actions: [],
    execute: { requiresConfirm: false, label: 'panel.doc_pdf_convert.execute' },
  }

  const handle: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => opts.isMultiSelect ?? false,
    getCurrentValues: () => ({ output_format: outputFormat.value }),
    setField: (field, value) => {
      switch (field) {
        case 'output_format': outputFormat.value = String(value); return outputFormat.value
        default: throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() { useAgentPanelHost('document.pdf_convert', handle); return {} },
    template: '<div></div>',
  })
}

describe('DocumentPdfConvertPanel agent integration', () => {
  beforeEach(() => { panelRegistry._clearAll() })

  it('registers handle on mount', () => {
    mount(makeDocumentPdfConvertPanelStub())
    expect(panelRegistry.get('document.pdf_convert')?.agentSchema.panelId).toBe('document.pdf_convert')
  })

  it('exposes 1 field (output_format)', () => {
    mount(makeDocumentPdfConvertPanelStub())
    const handle = panelRegistry.get('document.pdf_convert')!
    expect(handle.agentSchema.fields.map(f => f.name)).toEqual(['output_format'])
  })

  it('execute schema: confirm=false, doc_pdf_convert label', () => {
    mount(makeDocumentPdfConvertPanelStub())
    const handle = panelRegistry.get('document.pdf_convert')!
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: false, label: 'panel.doc_pdf_convert.execute' })
  })

  it('setField output_format updates', () => {
    mount(makeDocumentPdfConvertPanelStub())
    const handle = panelRegistry.get('document.pdf_convert')!
    expect(handle.setField('output_format', 'md')).toBe('md')
    expect(handle.getCurrentValues().output_format).toBe('md')
  })

  it('setField throws on unknown', () => {
    mount(makeDocumentPdfConvertPanelStub())
    const handle = panelRegistry.get('document.pdf_convert')!
    expect(() => handle.setField('bogus', 'x')).toThrow('Unknown field: bogus')
  })

  it('unmount removes handle', () => {
    const wrapper = mount(makeDocumentPdfConvertPanelStub())
    expect(panelRegistry.get('document.pdf_convert')).toBeTruthy()
    wrapper.unmount()
    expect(panelRegistry.get('document.pdf_convert')).toBeUndefined()
  })

  it('isMultiSelect=true → reports multi', () => {
    mount(makeDocumentPdfConvertPanelStub({ isMultiSelect: true }))
    const handle = panelRegistry.get('document.pdf_convert')!
    expect(handle.isMultiSelect()).toBe(true)
  })
})
