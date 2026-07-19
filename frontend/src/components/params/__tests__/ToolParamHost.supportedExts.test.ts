/**
 * ToolParamHost 副檔名 guard（v1.7.1 F）+ inheritAttrs/$attrs fallthrough 回歸鎖。
 * mock 佈局沿 ToolParamHost.test.ts。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, type PropType } from 'vue'
import type { ToolParamMeta } from '@/components/params/types'
import { PARAM_COMPONENTS, METAS } from '@/components/params/index'

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))

const isProcessingState = vi.hoisted(() => ({ value: false }))
vi.mock('@/composables/useSubmitTask', () => ({
  useSubmitTask: () => ({ submitTask: vi.fn(), isProcessing: isProcessingState }),
}))
vi.mock('@/composables/useAgentPanelHost', () => ({ useAgentPanelHost: () => {} }))
vi.mock('@/composables/useModelGuard', () => ({ useModelGuard: () => ({ guardModelReady: vi.fn(async () => true) }) }))
vi.mock('@/stores/models', () => ({ useModelStore: () => ({ models: [] }) }))

import ToolParamHost from '@/components/params/ToolParamHost.vue'

// stub 參數元件：宣告一個 probe attr 以驗證 fallthrough
const StubParams = defineComponent({
  name: 'StubParams',
  props: {
    params: { type: Object as PropType<Record<string, unknown>>, required: true },
    context: { type: String, required: true },
    fileInfo: { type: Object as PropType<Record<string, unknown> | null>, default: null },
    probeAttr: { type: String, default: '' },
  },
  emits: ['update:params'],
  render() {
    return h('div', { class: 'stub-params', 'data-probe': this.probeAttr })
  },
})

function makeMeta(overrides: Partial<ToolParamMeta> = {}): ToolParamMeta {
  return {
    toolKey: 'test.ext',
    apiPath: '/test/ext',
    labelKey: 'test.ext.label',
    taskType: 'test.ext',
    schema: [{ name: 'a', type: 'number', default: 1 }],
    defaults() { return { a: 1 } },
    multiSelect: false,
    ...overrides,
  }
}

const NO_EXTS = 'test.ext.none'
const WITH_EXTS = 'test.ext.pdf'
METAS[NO_EXTS] = makeMeta({ toolKey: NO_EXTS })
PARAM_COMPONENTS[NO_EXTS] = StubParams
METAS[WITH_EXTS] = makeMeta({ toolKey: WITH_EXTS, supportedExts: ['pdf'] })
PARAM_COMPONENTS[WITH_EXTS] = StubParams

function mountHost(toolKey: string, props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: { toolKey, panelId: toolKey, fileId: 'f1', currentFileName: 'x.pdf', fileInfo: null, ...props },
  })
}

beforeEach(() => { isProcessingState.value = false })

describe('ToolParamHost — supportedExts guard', () => {
  it('(a) META 無 supportedExts → 任意副檔名不 disable、無警示', () => {
    const w = mountHost(NO_EXTS, { currentFileName: 'x.xyz' })
    expect((w.vm as any).isDisabled).toBe(false)
    expect(w.find('.info-box--warn').exists()).toBe(false)
  })

  it('(b) supportedExts 命中 → 不因格式 disable、無警示', () => {
    const w = mountHost(WITH_EXTS, { currentFileName: 'doc.pdf' })
    expect((w.vm as any).isDisabled).toBe(false)
    expect(w.find('.info-box--warn').exists()).toBe(false)
  })

  it('(c) supportedExts 未命中＋有 fileId → isDisabled true＋警示框（文字為 ${toolKey}.format_not_supported）', () => {
    const w = mountHost(WITH_EXTS, { currentFileName: 'a.txt', fileId: 'f1' })
    expect((w.vm as any).isDisabled).toBe(true)
    const warn = w.find('.info-box--warn')
    expect(warn.exists()).toBe(true)
    expect(warn.text()).toContain(`${WITH_EXTS}.format_not_supported`)
  })

  it('(d) 未命中但 fileId=null（空狀態）→ 無警示框', () => {
    const w = mountHost(WITH_EXTS, { currentFileName: 'a.txt', fileId: null })
    expect(w.find('.info-box--warn').exists()).toBe(false)
  })
})

describe('ToolParamHost — inheritAttrs/$attrs fallthrough（B1 回歸鎖）', () => {
  it('未宣告於 host 的 attr 透過 $attrs 落到子參數元件', () => {
    const w = mountHost(NO_EXTS, { probeAttr: 'hello' } as Record<string, unknown>)
    const stub = w.find('.stub-params')
    expect(stub.attributes('data-probe')).toBe('hello')
  })
})
