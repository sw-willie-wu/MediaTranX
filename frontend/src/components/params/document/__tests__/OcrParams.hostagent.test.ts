/**
 * ToolParamHost + OcrParams 合掛整合測（統一參數元件 spec §6；批 4 Task 4.4）。
 * 覆蓋 document.ocr 掛載（toolKey='document.ocr'）：agentSchema 兩層合成（composite 覆蓋
 * 七欄）、setField、execute payload、downloadFormatField 契約（outputFormat expose）、
 * modelRequirement preflight（remote 短路、slot=ocr→category=llm）。
 * image.ocr 的等價掛載另見 image/__tests__/OcrParams.image.hostagent.test.ts（同一份共用
 * 元件、不同 toolKey，兩邊各驗證一次避免遺漏 registry 註冊）。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

const submitTaskMock = vi.hoisted(() => vi.fn())
const isProcessingState = vi.hoisted(() => ({ value: false }))
vi.mock('@/composables/useSubmitTask', () => ({
  useSubmitTask: () => ({ submitTask: submitTaskMock, isProcessing: isProcessingState }),
}))

const capturedHandle = vi.hoisted(() => ({ current: null as any }))
vi.mock('@/composables/useAgentPanelHost', () => ({
  useAgentPanelHost: (_panelId: string, handle: any) => {
    capturedHandle.current = handle
  },
}))

const guardModelReadyMock = vi.hoisted(() => vi.fn(async () => true))
vi.mock('@/composables/useModelGuard', () => ({
  useModelGuard: () => ({ guardModelReady: guardModelReadyMock }),
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
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    models: modelsState.models,
    byCapability: (cap: string) => modelsState.models.filter((m) => m.capabilities?.includes(cap)),
    forPanel: (items: unknown[]) => items,
    ensureLoaded: ensureLoadedMock,
  }),
}))
const remoteEnsureLoadedMock = vi.hoisted(() => vi.fn())
vi.mock('@/stores/remoteModels', () => ({
  useRemoteModelStore: () => ({
    byCapability: () => [],
    ensureLoaded: remoteEnsureLoadedMock,
  }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
// 靜態 import 讓 OcrParams.vue 先進 vitest 模組快取——見 CutParams.hostagent.test.ts
// 檔頭記載的動態 import race 問題與解法。
import '@/components/params/document/OcrParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'document.ocr',
      panelId: 'document.ocr',
      fileId: 'f1',
      currentFileName: 'report.pdf',
      ...props,
    },
    global: {
      mocks: { $t: (k: string) => k },
    },
  })
}

beforeEach(() => {
  submitTaskMock.mockReset()
  isProcessingState.value = false
  capturedHandle.current = null
  guardModelReadyMock.mockReset()
  guardModelReadyMock.mockResolvedValue(true)
  modelsState.models = []
  ensureLoadedMock.mockClear()
  remoteEnsureLoadedMock.mockClear()
  localStorage.clear()
})

describe('document.ocr × ToolParamHost — agentSchema 兩層合成', () => {
  it('1. fields 無裸 model_family/model_size/quantization/remote/provider/conn_id/remote_model（composite 覆蓋為 model）；有 output_format', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const fields = handle.agentSchema.fields
    const names = fields.map((f: any) => f.name)
    for (const covered of ['model_family', 'model_size', 'quantization', 'remote', 'provider', 'conn_id', 'remote_model']) {
      expect(names).not.toContain(covered)
    }
    expect(names).toContain('model')
    expect(names).toContain('output_format')

    w.unmount()
  })

  it('2. execute.label === panel.doc_ocr.execute（agentExecuteLabel 選配欄位）', async () => {
    const w = mountHost()
    await flushPromises()
    expect(capturedHandle.current.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.doc_ocr.execute' })
    w.unmount()
  })
})

describe('document.ocr × ToolParamHost — outputFormat expose（downloadFormatField 契約）', () => {
  it('3. host.outputFormat === params.output_format（TextPreviewModal 消費）', async () => {
    const w = mountHost()
    await flushPromises()
    expect((w.vm as any).outputFormat).toBe('md')
    ;(w.vm as any).setField('output_format', 'txt')
    await flushPromises()
    expect((w.vm as any).outputFormat).toBe('txt')
    w.unmount()
  })
})

describe('document.ocr × ToolParamHost — setField(model, token) → 七欄展開', () => {
  it('4. setField(model, "gemma4:9b") → getParams 反映 model_family/model_size', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('model', 'gemma4:9b')
    const p = (w.vm as any).getParams()
    expect(p.model_family).toBe('gemma4')
    expect(p.model_size).toBe('9b')
    expect(p.remote).toBe(false)

    w.unmount()
  })
})

describe('document.ocr × ToolParamHost — execute', () => {
  it('5. execute() → submitTask 收到 {file_id, output_format, model_family, model_size}', async () => {
    submitTaskMock.mockResolvedValue('tid1')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    handle.setField('model', 'gemma4:9b')

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledTimes(1)
    const [apiPath, payload, labelKey, taskType, fileName] = submitTaskMock.mock.calls[0]
    expect(apiPath).toBe('/document/ocr')
    expect(payload.file_id).toBe('f1')
    expect(payload.output_format).toBe('md')
    expect(payload.model_family).toBe('gemma4')
    expect(payload.model_size).toBe('9b')
    expect(labelKey).toBe('document.ocr.task_label')
    expect(taskType).toBe('document.ocr')
    expect(fileName).toBe('report.pdf')
    expect(result).toEqual({ task_id: 'tid1' })
    expect(w.emitted('submit')).toEqual([['tid1']])

    w.unmount()
  })
})

describe('document.ocr × ToolParamHost — preflight（modelRequirement，slot=ocr→category=llm）', () => {
  it('6a. remote=true → 跳過 guard（modelRequirement 回 null），直接送出', async () => {
    submitTaskMock.mockResolvedValue('tid-remote')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    handle.setField('model', 'remote:openai:1:gpt-4o')

    guardModelReadyMock.mockClear()
    const result = await handle.execute()

    expect(guardModelReadyMock).not.toHaveBeenCalled()
    expect(submitTaskMock).toHaveBeenCalled()
    expect(result).toEqual({ task_id: 'tid-remote' })

    w.unmount()
  })

  it('6b. 本地模型未下載 → guardModelReady(false, "llm")，execute 不送出', async () => {
    guardModelReadyMock.mockResolvedValueOnce(false)
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledWith(false, 'llm')
    expect(submitTaskMock).not.toHaveBeenCalled()
    expect(result).toEqual({})

    w.unmount()
  })

  it('6c. 本地模型已下載（family/size 相符）→ guardModelReady(true, "llm")，execute 正常送出', async () => {
    modelsState.models = [{ family: 'gemma4', variant: '4b:Q4_K_M', label: 'Gemma 4B', downloaded: true, capabilities: ['vision'] }]
    submitTaskMock.mockResolvedValue('tid2')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledWith(true, 'llm')
    expect(submitTaskMock).toHaveBeenCalled()
    expect(result).toEqual({ task_id: 'tid2' })

    w.unmount()
  })
})

describe('document.ocr × ToolParamHost — persist-key/i18n-prefix fallthrough attrs（DocumentView.vue 實際掛法）', () => {
  it('7. ToolParamHost 上的 kebab-case persist-key/i18n-prefix 透過 $attrs fallthrough 轉發到 OcrParams（同 field-group 先例）', async () => {
    modelsState.models = [
      { family: 'gemma4', variant: '4b:Q4_K_M', label: 'Gemma 4B', downloaded: true, capabilities: ['vision'] },
    ]
    const w = mountHost({ 'persist-key': 'doc_ocr_model', 'i18n-prefix': 'document.ocr' })
    await flushPromises()

    // fallback watch 選中第一個已下載模型後應寫入正確的 persist-key（若 fallthrough 失效，
    // 元件內部會退回硬編預設 'doc_ocr_model'——這裡刻意用不同字面值驗證真的有轉發，而非
    // 巧合命中同一個 fallback 預設值）。
    expect(localStorage.getItem('doc_ocr_model')).toBe('gemma4:4b')
    expect(w.text()).toContain('document.ocr.title')

    w.unmount()
  })

  it("8. persist-key='image_ocr_model' 轉發後寫入該 key（非退回 doc_ocr_model 預設）", async () => {
    modelsState.models = [
      { family: 'gemma4', variant: '4b:Q4_K_M', label: 'Gemma 4B', downloaded: true, capabilities: ['vision'] },
    ]
    const w = mountHost({ 'persist-key': 'image_ocr_model', 'i18n-prefix': 'image.ocr' })
    await flushPromises()

    expect(localStorage.getItem('image_ocr_model')).toBe('gemma4:4b')
    expect(localStorage.getItem('doc_ocr_model')).toBeNull()
    expect(w.text()).toContain('image.ocr.title')

    w.unmount()
  })
})
