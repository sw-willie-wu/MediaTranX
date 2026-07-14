/**
 * ToolParamHost + TranslateParams 合掛整合測（統一參數元件 spec §6 Major 2；批 1 Task 1.5——
 * model picker composite agent 欄位「首用」打樣，之後 6 個模型系工具面板套用同一測試 pattern）。
 * 仿 CutParams.hostagent.test.ts/TranscodeParams.hostagent.test.ts：不 stub 參數元件，
 * PARAM_COMPONENTS['document.translate'] 是 defineAsyncComponent 懶載真實 TranslateParams.vue，
 * 靜態 import 先進模組快取＋一次 flushPromises() 等掛載完成。
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

const modelsState = vi.hoisted(() => ({
  models: [] as Array<{ family: string; variant: string; label: string; size_mb: number; downloaded: boolean; capabilities?: string[] }>,
}))
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    models: modelsState.models,
    byCapability: (cap: string) => modelsState.models.filter((m) => m.capabilities?.includes(cap)),
    forPanel: (items: unknown[]) => items,
    ensureLoaded: vi.fn(),
  }),
}))

vi.mock('@/stores/remoteModels', () => ({
  useRemoteModelStore: () => ({
    byCapability: () => [] as unknown[],
    ensureLoaded: vi.fn(),
  }),
}))

vi.mock('@/composables/useApi', () => ({
  apiFetch: vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
// 靜態 import 讓 TranslateParams.vue 先進 vitest 模組快取（同一 resolved path）——見
// CutParams.hostagent.test.ts 檔頭記載的動態 import race 問題與解法。
import '@/components/params/document/TranslateParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'document.translate',
      panelId: 'document.translate',
      fileId: 'f1',
      currentFileName: 'report.pdf',
      fileInfo: null,
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
  localStorage.clear()
})

describe('TranslateParams × ToolParamHost — agentSchema 兩層合成', () => {
  it('1. fields 無七個後端 model 欄位；有 translate_model（enum，options() 回清單）＋一般欄位', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const names = handle.agentSchema.fields.map((f: any) => f.name)
    for (const covered of ['model_family', 'model_size', 'quantization', 'remote', 'provider', 'conn_id', 'remote_model']) {
      expect(names).not.toContain(covered)
    }
    expect(names).toContain('translate_model')
    expect(names).toEqual(expect.arrayContaining(['source_language', 'target_language', 'translate_style']))
    // glossary 是 dict 型欄位——review finding #2：agent 的 set_field 是 scalar，無法表達 dict，
    // 曝出去會讓使用者傳字串進去、後端 422；舊 DocumentTranslatePanel 本就不曝露 glossary 給 agent。
    expect(names).not.toContain('glossary')

    const modelField = handle.agentSchema.fields.find((f: any) => f.name === 'translate_model')
    expect(modelField.type).toBe('enum')
    expect(typeof modelField.options).toBe('function')

    w.unmount()
  })
})

describe('TranslateParams × ToolParamHost — setField(translate_model, token)', () => {
  it('2. setField(translate_model, "gemma4:4b:q4") → params 七欄正確展開（local 分支，remote 欄清除）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('translate_model', 'gemma4:4b:q4')
    const params = (w.vm as any).getParams()
    expect(params.model_family).toBe('gemma4')
    expect(params.model_size).toBe('4b')
    expect(params.quantization).toBe('q4')
    expect(params.remote).toBe(false)
    expect(params.provider).toBeUndefined()
    expect(params.conn_id).toBeUndefined()
    expect(params.remote_model).toBeUndefined()

    w.unmount()
  })

  it('3. setField(translate_model, "remote:openai:1:gpt-4o") → remote 分支展開＋local 欄清除', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('translate_model', 'remote:openai:1:gpt-4o')
    const params = (w.vm as any).getParams()
    expect(params.remote).toBe(true)
    expect(params.provider).toBe('openai')
    expect(params.conn_id).toBe(1)
    expect(params.remote_model).toBe('gpt-4o')
    expect(params.model_family).toBeUndefined()
    expect(params.model_size).toBeUndefined()
    expect(params.quantization).toBeUndefined()

    w.unmount()
  })
})

describe('TranslateParams × ToolParamHost — getCurrentValues', () => {
  it('4. getCurrentValues().translate_model === encode 現值；七個 covers 欄位不出現', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('translate_model', 'remote:gemini:2:gemini-1.5-pro')
    const values = handle.getCurrentValues()
    expect(values.translate_model).toBe('remote:gemini:2:gemini-1.5-pro')
    for (const covered of ['model_family', 'model_size', 'quantization', 'remote', 'provider', 'conn_id', 'remote_model']) {
      expect(values).not.toHaveProperty(covered)
    }

    w.unmount()
  })
})

describe('TranslateParams × ToolParamHost — execute', () => {
  it('5. execute（mock submitTask）payload 含 file_id＋params 全集（glossary dict 原樣）', async () => {
    submitTaskMock.mockResolvedValue('tid1')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('translate_model', 'gemma4:4b:Q4_K_M')
    ;(w.vm as any).setField('source_language', 'en')
    ;(w.vm as any).setField('target_language', 'zh-TW')
    ;(w.vm as any).setParams({ ...(w.vm as any).getParams(), glossary: { API: '介面' } })

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledTimes(1)
    const [apiPath, payload, labelKey, taskType, fileName] = submitTaskMock.mock.calls[0]
    expect(apiPath).toBe('/document/translate')
    expect(payload.file_id).toBe('f1')
    expect(payload.model_family).toBe('gemma4')
    expect(payload.model_size).toBe('4b')
    expect(payload.quantization).toBe('Q4_K_M')
    expect(payload.source_language).toBe('en')
    expect(payload.target_language).toBe('zh-TW')
    expect(payload.glossary).toEqual({ API: '介面' })
    expect(labelKey).toBe('document.translate.task_label')
    expect(taskType).toBe('document.translate')
    expect(fileName).toBe('report.pdf')
    expect(result).toEqual({ task_id: 'tid1' })
    expect(w.emitted('submit')).toEqual([['tid1']])

    w.unmount()
  })
})

describe('TranslateParams × ToolParamHost — preflight（local 未安裝走 guard；remote 直過）', () => {
  it('6a. local 分支，modelStore 無對應已下載模型 → guardModelReady(false, "llm")，execute 不送出', async () => {
    guardModelReadyMock.mockResolvedValueOnce(false)
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('translate_model', 'gemma4:27b:Q4_K_M')
    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledWith(false, 'llm')
    expect(submitTaskMock).not.toHaveBeenCalled()
    expect(result).toEqual({})

    w.unmount()
  })

  it('6b. local 分支，modelStore 有對應已下載模型 → guardModelReady(true, "llm")，execute 正常送出', async () => {
    modelsState.models = [{ family: 'gemma4', variant: '4b:Q4_K_M', label: 'Gemma4 4B', size_mb: 3000, downloaded: true, capabilities: ['text'] }]
    submitTaskMock.mockResolvedValue('tid2')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('translate_model', 'gemma4:4b:Q4_K_M')
    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledWith(true, 'llm')
    expect(submitTaskMock).toHaveBeenCalled()
    expect(result).toEqual({ task_id: 'tid2' })

    w.unmount()
  })

  it('6c. remote 分支 → preflight 不呼叫 guardModelReady，直接放行', async () => {
    submitTaskMock.mockResolvedValue('tid3')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('translate_model', 'remote:openai:1:gpt-4o')
    guardModelReadyMock.mockClear()
    const result = await handle.execute()

    expect(guardModelReadyMock).not.toHaveBeenCalled()
    expect(submitTaskMock).toHaveBeenCalled()
    expect(result).toEqual({ task_id: 'tid3' })

    w.unmount()
  })
})
