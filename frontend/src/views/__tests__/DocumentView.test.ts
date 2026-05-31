import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { viewRegistry } from '@/stores/viewRegistry'
import { useViewHost } from '@/composables/useViewHost'

function makeDocumentViewStub(opts: { initialFunction?: string } = {}) {
  const currentFunction = ref(opts.initialFunction ?? 'split')

  return defineComponent({
    setup() {
      useViewHost('document', {
        currentFunction,
        setCurrentFunction: (id) => { currentFunction.value = id },
        validSubfunctions: () => ['split', 'pdf-convert', 'ocr', 'translate'],
      })
      return { currentFunction }
    },
    template: '<div></div>',
  })
}

describe('DocumentView agent integration (useViewHost wire)', () => {
  beforeEach(() => { viewRegistry._clearAll?.() })

  it('registers ViewHandle on mount', () => {
    mount(makeDocumentViewStub())
    const handle = viewRegistry.get('document')
    expect(handle).toBeTruthy()
    expect(handle?.validSubfunctions?.()).toEqual(['split', 'pdf-convert', 'ocr', 'translate'])
  })

  it('setCurrentFunction switches subfunction', () => {
    mount(makeDocumentViewStub())
    const handle = viewRegistry.get('document')!
    handle.setCurrentFunction('translate')
    expect(handle.currentFunction.value).toBe('translate')
    handle.setCurrentFunction('ocr')
    expect(handle.currentFunction.value).toBe('ocr')
  })

  it('validSubfunctions uses dash-case for pdf-convert', () => {
    mount(makeDocumentViewStub())
    const handle = viewRegistry.get('document')!
    const subs = handle.validSubfunctions?.() ?? []
    expect(subs).toContain('pdf-convert')
    expect(subs).not.toContain('pdf_convert')
  })

  it('unmount removes from registry', () => {
    const wrapper = mount(makeDocumentViewStub())
    expect(viewRegistry.get('document')).toBeTruthy()
    wrapper.unmount()
    expect(viewRegistry.get('document')).toBeUndefined()
  })
})
