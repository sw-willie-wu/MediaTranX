/**
 * ToolParamHost + SummaryParams 合掛整合測（統一參數元件 spec §6；批 2 Task 2.4——批 2
 * 最大工具：三模型 composite ＋ host modelRequirements 複數擴充首用）。
 * 取代舊 VideoSummaryPanel.agent.test.ts（純 stub handle 測試）——host 接手 agent 掛載後，
 * 唯一權威測試點改用真實 SummaryParams.vue（同 TranslateParams.hostagent.test.ts 模式）。
 * 不 stub 參數元件：PARAM_COMPONENTS['video.summary'] 是 defineAsyncComponent 懶載真實
 * SummaryParams.vue，靜態 import 先進模組快取＋一次 flushPromises() 等掛載完成。
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
  models: [] as Array<{
    family: string
    variant: string
    label: string
    size_mb: number
    downloaded: boolean
    capabilities?: string[]
    category?: string
    subcategory?: string
  }>,
}))
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    models: modelsState.models,
    byCapability: (cap: string) => modelsState.models.filter((m) => m.capabilities?.includes(cap)),
    byCategory: (cat: string) => modelsState.models.filter((m) => m.category === cat),
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

import ToolParamHost from '@/components/params/ToolParamHost.vue'
// 靜態 import 讓 SummaryParams.vue 先進 vitest 模組快取（同一 resolved path）——見
// CutParams.hostagent.test.ts 檔頭記載的動態 import race 問題與解法。
import '@/components/params/video/SummaryParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'video.summary',
      panelId: 'video.summary',
      fileId: 'f1',
      currentFileName: 'clip.mp4',
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

describe('SummaryParams × ToolParamHost — agentSchema 兩層合成', () => {
  it('1. fields 無 18 個後端 model 欄位；有 whisper_model/llm_model/vlm_model 三個 composite＋一般欄位', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const names = handle.agentSchema.fields.map((f: any) => f.name)
    const covered = [
      'whisper_model_size',
      'llm_model_family', 'llm_model_size', 'llm_remote', 'llm_provider', 'llm_conn_id', 'llm_remote_model',
      'vlm_model_family', 'vlm_model_size', 'vlm_remote', 'vlm_provider', 'vlm_conn_id', 'vlm_remote_model',
    ]
    for (const c of covered) expect(names).not.toContain(c)

    expect(names).toContain('whisper_model')
    expect(names).toContain('llm_model')
    expect(names).toContain('vlm_model')
    expect(names).toEqual(expect.arrayContaining(['summary_mode', 'vocal_separation', 'align', 'language']))

    for (const compositeName of ['whisper_model', 'llm_model', 'vlm_model']) {
      const f = handle.agentSchema.fields.find((x: any) => x.name === compositeName)
      expect(f.type).toBe('enum')
      expect(typeof f.options).toBe('function')
    }

    w.unmount()
  })

  it('2. execute.label === panel.summary.execute（agentExecuteLabel 選配欄位）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.summary.execute' })
    w.unmount()
  })
})

describe('SummaryParams × ToolParamHost — setField(whisper_model/llm_model/vlm_model, token)', () => {
  it('3a. setField(whisper_model, "small") → params.whisper_model_size 更新', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('whisper_model', 'small')
    expect((w.vm as any).getParams().whisper_model_size).toBe('small')
  })

  it('3b. setField(llm_model, "gemma4:9b") → 六欄正確展開（local 分支，remote 欄清除）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('llm_model', 'gemma4:9b')
    const params = (w.vm as any).getParams()
    expect(params.llm_model_family).toBe('gemma4')
    expect(params.llm_model_size).toBe('9b')
    expect(params.llm_remote).toBe(false)
    expect(params.llm_provider).toBeUndefined()
    expect(params.llm_conn_id).toBeUndefined()
    expect(params.llm_remote_model).toBeUndefined()
  })

  it('3c. setField(vlm_model, "remote:openai:1:gpt-4o") → remote 分支展開＋local 欄清除', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('vlm_model', 'remote:openai:1:gpt-4o')
    const params = (w.vm as any).getParams()
    expect(params.vlm_remote).toBe(true)
    expect(params.vlm_provider).toBe('openai')
    expect(params.vlm_conn_id).toBe(1)
    expect(params.vlm_remote_model).toBe('gpt-4o')
    expect(params.vlm_model_family).toBeUndefined()
    expect(params.vlm_model_size).toBeUndefined()
  })

  it('3d. setField(vlm_model, "") → vlm 六欄全清（不使用 VLM）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('vlm_model', 'qwen3vl:8b')
    expect((w.vm as any).getParams().vlm_model_family).toBe('qwen3vl')
    handle.setField('vlm_model', '')
    const params = (w.vm as any).getParams()
    expect(params.vlm_model_family).toBeUndefined()
    expect(params.vlm_model_size).toBeUndefined()
  })

  it('3e. setField(summary_mode, "narrative") → 直寫（非 composite）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('summary_mode', 'narrative')
    expect((w.vm as any).getParams().summary_mode).toBe('narrative')
  })
})

describe('SummaryParams × ToolParamHost — getCurrentValues', () => {
  it('4. getCurrentValues() 三個 composite 欄位 = encode 現值；18 個 covers 欄位不出現', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('whisper_model', 'small')
    handle.setField('llm_model', 'gemma4:9b')
    handle.setField('vlm_model', 'remote:gemini:2:gemini-1.5-pro')

    const values = handle.getCurrentValues()
    expect(values.whisper_model).toBe('small')
    expect(values.llm_model).toBe('gemma4:9b')
    expect(values.vlm_model).toBe('remote:gemini:2:gemini-1.5-pro')

    const covered = [
      'whisper_model_size',
      'llm_model_family', 'llm_model_size', 'llm_remote', 'llm_provider', 'llm_conn_id', 'llm_remote_model',
      'vlm_model_family', 'vlm_model_size', 'vlm_remote', 'vlm_provider', 'vlm_conn_id', 'vlm_remote_model',
    ]
    for (const c of covered) expect(values).not.toHaveProperty(c)

    w.unmount()
  })
})

describe('SummaryParams × ToolParamHost — execute', () => {
  it('5. execute（mock submitTask）payload 含 file_id＋params 全集', async () => {
    submitTaskMock.mockResolvedValue('tid1')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('whisper_model', 'medium')
    handle.setField('llm_model', 'gemma4:9b')
    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledTimes(1)
    const [apiPath, payload, labelKey, taskType, fileName] = submitTaskMock.mock.calls[0]
    expect(apiPath).toBe('/video/summary')
    expect(payload.file_id).toBe('f1')
    expect(payload.whisper_model_size).toBe('medium')
    expect(payload.llm_model_family).toBe('gemma4')
    expect(payload.llm_model_size).toBe('9b')
    expect(labelKey).toBe('video.summary.task_label')
    expect(taskType).toBe('video.summary')
    expect(fileName).toBe('clip.mp4')
    expect(result).toEqual({ task_id: 'tid1' })
    expect(w.emitted('submit')).toEqual([['tid1']])

    w.unmount()
  })
})

describe('SummaryParams × ToolParamHost — preflight（modelRequirements 複數，五道 guard 依序）', () => {
  it('6a. 最小案（無 vocal_separation/align/vlm）：whisper 未安裝 → 只呼叫一次 guardModelReady(false,"audio")，execute 不送出', async () => {
    guardModelReadyMock.mockResolvedValueOnce(false)
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('llm_model', 'gemma4:9b')
    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledTimes(1)
    expect(guardModelReadyMock).toHaveBeenCalledWith(false, 'audio')
    expect(submitTaskMock).not.toHaveBeenCalled()
    expect(result).toEqual({})

    w.unmount()
  })

  it('6b. whisper 已安裝、llm 未安裝 → 恰呼叫兩次（audio→llm），execute 不送出', async () => {
    modelsState.models = [
      { family: 'whisper', variant: 'medium', label: 'Medium', size_mb: 100, downloaded: true, category: 'stt' },
    ]
    guardModelReadyMock.mockResolvedValueOnce(true).mockResolvedValueOnce(false)
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('llm_model', 'gemma4:9b')
    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledTimes(2)
    expect(guardModelReadyMock).toHaveBeenNthCalledWith(1, true, 'audio')
    expect(guardModelReadyMock).toHaveBeenNthCalledWith(2, false, 'llm')
    expect(result).toEqual({})

    w.unmount()
  })

  it('6c. whisper+llm 皆已安裝 → guardModelReady 兩次皆 true，execute 正常送出', async () => {
    modelsState.models = [
      { family: 'whisper', variant: 'medium', label: 'Medium', size_mb: 100, downloaded: true, category: 'stt' },
      { family: 'gemma4', variant: '9b:Q4_K_M', label: 'Gemma4 9B', size_mb: 3000, downloaded: true, capabilities: ['text'] },
    ]
    submitTaskMock.mockResolvedValue('tid2')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('llm_model', 'gemma4:9b')
    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledTimes(2)
    expect(submitTaskMock).toHaveBeenCalled()
    expect(result).toEqual({ task_id: 'tid2' })

    w.unmount()
  })

  it('6d. vocal_separation=true 且 demucs 未安裝 → 第二道（separate→audio）擋下，第三道（llm）不檢查', async () => {
    modelsState.models = [
      { family: 'whisper', variant: 'medium', label: 'Medium', size_mb: 100, downloaded: true, category: 'stt' },
    ]
    guardModelReadyMock.mockResolvedValueOnce(true).mockResolvedValueOnce(false)
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('vocal_separation', true)
    handle.setField('llm_model', 'gemma4:9b')
    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledTimes(2)
    expect(guardModelReadyMock).toHaveBeenNthCalledWith(2, false, 'audio')
    expect(result).toEqual({})

    w.unmount()
  })

  it('6e. align=true 且 alignment 分類任一模型已裝 → categories-only guard 通過（true, "audio"）', async () => {
    modelsState.models = [
      { family: 'whisper', variant: 'medium', label: 'Medium', size_mb: 100, downloaded: true, category: 'stt' },
      { family: 'wav2vec2', variant: 'base', label: 'wav2vec2', size_mb: 300, downloaded: true, category: 'alignment' },
      { family: 'gemma4', variant: '9b:Q4_K_M', label: 'Gemma4 9B', size_mb: 3000, downloaded: true, capabilities: ['text'] },
    ]
    submitTaskMock.mockResolvedValue('tid3')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('align', true)
    handle.setField('llm_model', 'gemma4:9b')
    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledTimes(3)
    expect(guardModelReadyMock).toHaveBeenNthCalledWith(2, true, 'audio') // align guard 通過
    expect(submitTaskMock).toHaveBeenCalled()
    expect(result).toEqual({ task_id: 'tid3' })

    w.unmount()
  })

  it('6f. llm remote → LLM guard 跳過；vlm 有 local 值時追加 vlm guard（slot=vlm→category=llm）', async () => {
    modelsState.models = [
      { family: 'whisper', variant: 'medium', label: 'Medium', size_mb: 100, downloaded: true, category: 'stt' },
    ]
    guardModelReadyMock.mockResolvedValueOnce(true).mockResolvedValueOnce(false)
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('llm_model', 'remote:openai:1:gpt-4o')
    handle.setField('vlm_model', 'qwen3vl:8b')
    const result = await handle.execute()

    // whisper(true,audio) → llm remote 跳過(不 push) → vlm(false,llm)
    expect(guardModelReadyMock).toHaveBeenCalledTimes(2)
    expect(guardModelReadyMock).toHaveBeenNthCalledWith(1, true, 'audio')
    expect(guardModelReadyMock).toHaveBeenNthCalledWith(2, false, 'llm')
    expect(result).toEqual({})

    w.unmount()
  })
})
