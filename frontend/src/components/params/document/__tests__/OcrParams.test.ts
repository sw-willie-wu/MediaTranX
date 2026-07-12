/**
 * OcrParams.vue 單測（統一參數元件案批 4 Task 4.4）——共用元件，document.ocr／image.ocr
 * 兩 toolKey 皆掛此檔。覆蓋：掛載載入模型清單、composite（7 欄 covers、token roundtrip）、
 * persistKey/i18nPrefix fallthrough props、tool/pipeline context persisted seed 分流。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import type { AgentCompositeField } from '../../types'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

interface FakeModel {
  family: string
  variant: string
  label: string
  downloaded: boolean
  capabilities?: string[]
}

const modelsState = vi.hoisted(() => ({ models: [] as FakeModel[] }))
const ensureLoadedMock = vi.hoisted(() => vi.fn())
const remoteEnsureLoadedMock = vi.hoisted(() => vi.fn())
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    byCapability: (cap: string) => modelsState.models.filter((m) => m.capabilities?.includes(cap)),
    forPanel: (items: unknown[]) => items,
    ensureLoaded: ensureLoadedMock,
  }),
}))
vi.mock('@/stores/remoteModels', () => ({
  useRemoteModelStore: () => ({
    byCapability: () => [],
    ensureLoaded: remoteEnsureLoadedMock,
  }),
}))

import OcrParams from '../OcrParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'

function mountParams(
  params: Record<string, unknown>,
  extra: Record<string, unknown> = {},
  onRegister?: (c: AgentCompositeField) => void,
) {
  return mount(OcrParams, {
    props: { params, context: 'tool', fileInfo: null, ...extra },
    global: {
      mocks: { $t: (k: string) => k },
      provide: {
        registerComposite: (c: AgentCompositeField) => {
          onRegister?.(c)
          return () => {}
        },
      },
    },
  })
}

const DEFAULTS = { output_format: 'md', model_size: '4b', remote: false }

beforeEach(() => {
  modelsState.models = []
  localStorage.clear()
  ensureLoadedMock.mockClear()
  remoteEnsureLoadedMock.mockClear()
})

describe('OcrParams — 掛載時載入模型清單（本地＋雲端）', () => {
  it('mount 後 modelStore.ensureLoaded 與 remoteStore.ensureLoaded 皆被呼叫', () => {
    mountParams(DEFAULTS)
    expect(ensureLoadedMock).toHaveBeenCalledTimes(1)
    expect(remoteEnsureLoadedMock).toHaveBeenCalledTimes(1)
  })
})

describe('OcrParams — composite 註冊（7 欄 covers）', () => {
  it("name='model'，covers 涵蓋七個後端欄位", () => {
    let captured: AgentCompositeField | null = null
    mountParams(DEFAULTS, {}, (c) => { captured = c })
    expect(captured!.name).toBe('model')
    expect(captured!.covers).toEqual([
      'model_family', 'model_size', 'quantization', 'remote', 'provider', 'conn_id', 'remote_model',
    ])
  })

  it('composite.get(params) === encodeModelToken(params)', () => {
    let captured: AgentCompositeField | null = null
    mountParams(DEFAULTS, {}, (c) => { captured = c })
    expect(captured!.get({ remote: false, model_family: 'gemma4', model_size: '9b' })).toBe('gemma4:9b')
  })

  it('composite.set(token) roundtrip：set→get 回原 token', () => {
    let captured: AgentCompositeField | null = null
    mountParams(DEFAULTS, {}, (c) => { captured = c })
    const patch = captured!.set('gemma4:9b')
    expect(captured!.get({ ...DEFAULTS, ...patch })).toBe('gemma4:9b')
  })

  it('composite.set(remote token) roundtrip', () => {
    let captured: AgentCompositeField | null = null
    mountParams(DEFAULTS, {}, (c) => { captured = c })
    const patch = captured!.set('remote:openai:3:gpt-4o')
    expect(captured!.get({ ...DEFAULTS, ...patch })).toBe('remote:openai:3:gpt-4o')
  })
})

describe('OcrParams — 選擇模型/輸出格式 → emit update:params', () => {
  it('選擇模型 picker → commitPatch 七欄', async () => {
    modelsState.models = [
      { family: 'gemma4', variant: '4b:Q4_K_M', label: 'Gemma 4B Q4', downloaded: true, capabilities: ['vision'] },
      { family: 'qwen3vl', variant: '9b:Q4_K_M', label: 'Qwen3VL 9B Q4', downloaded: true, capabilities: ['vision'] },
    ]
    const w = mountParams(DEFAULTS)
    const modelSelect = w.findAllComponents(AppSelect)[0]
    await modelSelect.vm.$emit('update:modelValue', 'qwen3vl:9b')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.model_family).toBe('qwen3vl')
    expect(last.model_size).toBe('9b')
  })

  it('切換輸出格式 → commitPatch({output_format})', async () => {
    const w = mountParams(DEFAULTS)
    const formatSelect = w.findAllComponents(AppSelect)[1]
    await formatSelect.vm.$emit('update:modelValue', 'txt')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.output_format).toBe('txt')
  })
})

describe('OcrParams — persistKey fallthrough prop（沿用舊字面值）', () => {
  it('persistKey="image_ocr_model" → 選模型後寫入該 key（非 doc_ocr_model）', async () => {
    modelsState.models = [
      { family: 'gemma4', variant: '4b:Q4_K_M', label: 'Gemma 4B Q4', downloaded: true, capabilities: ['vision'] },
      { family: 'qwen3vl', variant: '9b:Q4_K_M', label: 'Qwen3VL 9B Q4', downloaded: true, capabilities: ['vision'] },
    ]
    const w = mountParams(DEFAULTS, { persistKey: 'image_ocr_model' })
    const modelSelect = w.findAllComponents(AppSelect)[0]
    await modelSelect.vm.$emit('update:modelValue', 'qwen3vl:9b')
    expect(localStorage.getItem('image_ocr_model')).toBe('qwen3vl:9b')
    expect(localStorage.getItem('doc_ocr_model')).toBeNull()
  })

  it('未傳 persistKey → 退回 doc_ocr_model', async () => {
    modelsState.models = [
      { family: 'gemma4', variant: '4b:Q4_K_M', label: 'Gemma 4B Q4', downloaded: true, capabilities: ['vision'] },
      { family: 'qwen3vl', variant: '9b:Q4_K_M', label: 'Qwen3VL 9B Q4', downloaded: true, capabilities: ['vision'] },
    ]
    const w = mountParams(DEFAULTS)
    const modelSelect = w.findAllComponents(AppSelect)[0]
    await modelSelect.vm.$emit('update:modelValue', 'qwen3vl:9b')
    expect(localStorage.getItem('doc_ocr_model')).toBe('qwen3vl:9b')
  })
})

describe('OcrParams — i18nPrefix fallthrough prop（文案前綴）', () => {
  it('i18nPrefix="image.ocr" → 標題 key 帶 image.ocr 前綴', () => {
    const w = mountParams(DEFAULTS, { i18nPrefix: 'image.ocr' })
    expect(w.text()).toContain('image.ocr.title')
  })

  it('未傳 i18nPrefix → 退回 document.ocr 前綴', () => {
    const w = mountParams(DEFAULTS)
    expect(w.text()).toContain('document.ocr.title')
  })
})

describe('OcrParams — tool context：persisted seed（params===defaults 時才套用）', () => {
  it('localStorage 有值且 token===defaults token → 掛載時 seed patch', () => {
    localStorage.setItem('doc_ocr_model', 'gemma4:9b')
    const w = mountParams(DEFAULTS)
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.model_family).toBe('gemma4')
    expect(last.model_size).toBe('9b')
  })

  it('token 已非 defaults → 不套用 seed', () => {
    localStorage.setItem('doc_ocr_model', 'gemma4:9b')
    const w = mountParams({ ...DEFAULTS, model_family: 'qwen3vl', model_size: '4b' })
    const emitted = w.emitted('update:params')
    if (emitted) {
      const last = emitted[emitted.length - 1][0] as Record<string, unknown>
      expect(last.model_family).not.toBe('gemma4')
    }
  })
})

describe('OcrParams — pipeline context：無 persisted seed', () => {
  it('pipeline context 掛載不套用 localStorage seed', () => {
    localStorage.setItem('doc_ocr_model', 'gemma4:9b')
    const w = mountParams(DEFAULTS, { context: 'pipeline' })
    const emitted = w.emitted('update:params')
    if (emitted) {
      const last = emitted[emitted.length - 1][0] as Record<string, unknown>
      expect(last.model_family).not.toBe('gemma4')
    }
  })

  it('pipeline context 選擇模型不寫入 localStorage', async () => {
    modelsState.models = [
      { family: 'gemma4', variant: '4b:Q4_K_M', label: 'Gemma 4B Q4', downloaded: true, capabilities: ['vision'] },
    ]
    const w = mountParams(DEFAULTS, { context: 'pipeline' })
    const modelSelect = w.findAllComponents(AppSelect)[0]
    await modelSelect.vm.$emit('update:modelValue', 'gemma4:4b')
    expect(localStorage.getItem('doc_ocr_model')).toBeNull()
  })
})
