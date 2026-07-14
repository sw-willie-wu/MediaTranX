/**
 * ToolParamHost + TranscribeParams 合掛整合測（統一參數元件 spec §6；批 3 Task 3.4）。
 * 取代舊 AudioTranscribePanel.agent.test.ts（stub-based，僅測 useAgentPanelHost 契約）——
 * 這裡不 stub 參數元件，PARAM_COMPONENTS['audio.transcribe'] 是真實 TranscribeParams.vue
 * （沿 SeparateParams.hostagent.test.ts / VolumeParams.hostagent.test.ts 先例）。
 *
 * 覆蓋：三 composite 欄位不直曝（agent fields 縮小）、setField 走 composite/一般欄位兩路、
 * execute payload 完整形狀 vs 舊 body 等價、preflight 五道 guard（whisper→demucs→align→
 * translate→summarize，slot=summarize→category=llm 是本 task 新補的 SLOT_GUARD_CATEGORY）。
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

vi.mock('@/stores/settings', () => ({
  useSettingsStore: () => ({
    showAllModels: false,
    deviceInfo: null,
    loadDeviceInfo: vi.fn().mockResolvedValue(undefined),
  }),
}))

vi.mock('@/composables/useApi', () => ({
  apiFetch: vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
// 靜態 import 讓 TranscribeParams.vue 先進 vitest 模組快取（見 CutParams.hostagent.test.ts 同段註記）。
import '@/components/params/audio/TranscribeParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'audio.transcribe',
      panelId: 'audio.transcribe',
      fileId: 'f1',
      currentFileName: 'lecture.mp3',
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
})

describe('TranscribeParams × ToolParamHost — agentSchema（三 composite 縮小欄位曝光）', () => {
  it('1. fields = 13 一般欄位（非 covered、非 dict）+ 3 composite（whisper_model/translate_model/summarize_model）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const names = handle.agentSchema.fields.map((f: any) => f.name)
    expect(names).toEqual([
      'source_language', 'output_format', 'translate', 'target_language', 'keep_names', 'translate_style',
      'summarize', 'vocal_separation', 'word_timestamps', 'condition_on_previous_text',
      'min_silence_duration_ms', 'vad_threshold', 'align',
      'whisper_model', 'translate_model', 'summarize_model',
    ])
    // 覆蓋欄位（model_size + 七個 translate_* + 七個 summarize_*）與 dict 欄位（glossary）不直曝
    expect(names).not.toContain('model_size')
    expect(names).not.toContain('translate_model_family')
    expect(names).not.toContain('summarize_model_family')
    expect(names).not.toContain('glossary')

    w.unmount()
  })

  it('2. execute.label=panel.transcribe.execute；requiresConfirm 退回 host 預設 true（舊 panel 亦為 true）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.transcribe.execute' })
    w.unmount()
  })
})

describe('TranscribeParams × ToolParamHost — setField（composite 路徑 + 一般欄位路徑）', () => {
  it('3. setField(translate, true) → 一般 boolean 欄位路徑', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('translate', true)).toBe(true)
    expect(w.vm.params.translate).toBe(true)

    w.unmount()
  })

  it('4. setField(translate_model, "gemma4:4b:Q4_K_M") → composite 展開七欄（不含 translate bool 本身）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('translate_model', 'gemma4:4b:Q4_K_M')

    expect(w.vm.params.translate_model_family).toBe('gemma4')
    expect(w.vm.params.translate_model_size).toBe('4b')
    expect(w.vm.params.translate_quantization).toBe('Q4_K_M')
    expect(w.vm.params.translate_remote).toBe(false)

    w.unmount()
  })

  it('5. setField(summarize_model, "remote:openai:1:gpt-4o") → composite 展開 remote 四欄', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('summarize_model', 'remote:openai:1:gpt-4o')

    expect(w.vm.params.summarize_remote).toBe(true)
    expect(w.vm.params.summarize_provider).toBe('openai')
    expect(w.vm.params.summarize_conn_id).toBe(1)
    expect(w.vm.params.summarize_remote_model).toBe('gpt-4o')

    w.unmount()
  })

  it('6. setField(whisper_model, "large-v3") → composite 覆蓋 model_size', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('whisper_model', 'large-v3')).toBe('large-v3')
    expect(w.vm.params.model_size).toBe('large-v3')

    w.unmount()
  })
})

describe('TranscribeParams × ToolParamHost — execute payload 完整形狀（vs 舊 AudioTranscribePanel body 等價）', () => {
  it('7. 最小狀態（無 translate/summarize）→ submitTask 收到 file_id + 基本欄位，無 translate_*/summarize_* 子欄', async () => {
    submitTaskMock.mockResolvedValue('tid-min')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/audio/transcribe',
      {
        file_id: 'f1',
        model_size: 'medium',
        output_format: 'txt',
        vocal_separation: false,
        word_timestamps: false,
        align: false,
        condition_on_previous_text: true,
        min_silence_duration_ms: 200,
        vad_threshold: 0.3,
        translate: false,
        summarize: false,
      },
      'audio.transcribe.task_label',
      'audio.transcribe',
      'lecture.mp3',
    )
    expect(result).toEqual({ task_id: 'tid-min' })
    expect(w.emitted('submit')).toEqual([['tid-min']])

    w.unmount()
  })

  it('8. translate+summarize 皆開（本地模型）→ payload 含完整雙組子欄', async () => {
    submitTaskMock.mockResolvedValue('tid-full')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('source_language', 'en')
    w.vm.setParams({
      ...w.vm.params,
      source_language: 'en',
      translate: true,
      target_language: 'zh-TW',
      translate_model_family: 'gemma4',
      translate_model_size: '4b',
      translate_quantization: 'Q4_K_M',
      keep_names: false,
      translate_style: 'formal',
      summarize: true,
      summarize_model_family: 'gemma4',
      summarize_model_size: '12b',
      summarize_quantization: 'Q8_0',
    })

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/audio/transcribe',
      expect.objectContaining({
        file_id: 'f1',
        source_language: 'en',
        translate: true,
        target_language: 'zh-TW',
        translate_model_family: 'gemma4',
        translate_model_size: '4b',
        translate_quantization: 'Q4_K_M',
        keep_names: false,
        translate_style: 'formal',
        summarize: true,
        summarize_model_family: 'gemma4',
        summarize_model_size: '12b',
        summarize_quantization: 'Q8_0',
      }),
      'audio.transcribe.task_label',
      'audio.transcribe',
      'lecture.mp3',
    )
    expect(result).toEqual({ task_id: 'tid-full' })

    w.unmount()
  })

  // buildSubmit 的雙重判準（translate===true && target_language 有值）在真機掛載下無法從
  // hostagent 層隔離驗證：TranscribeParams.vue 掛載的 TranslationOptionsPanel 是受控元件，
  // setParams({translate:true, target_language:''}) 一落地就會經 translationValue computed
  // →TranslationOptionsPanel 內部 fallback（v.target_language || 'zh-TW'）→自己的內部 watch
  // 立即 emit 回 onTranslationChange，把 target_language 正規化回 'zh-TW'（與 UI 手動開啟翻譯
  // 的行為一致，見 TranscribeParams.vue onTranslationChange 註解）。這個雙重判準的分支已在
  // transcribe.meta.test.ts「translate=true 但 target_language 空」直接測 buildSubmit 純函式
  // 覆蓋（bypass 元件反應鏈），此處不重複（重複會斷言到元件正規化後的值，語意不同、會誤導）。
})

describe('TranscribeParams × ToolParamHost — preflight 五道 guard（whisper→demucs→align→translate→summarize）', () => {
  it('10a. whisper 模型未下載 → guardModelReady(false, "audio")，execute 不送出', async () => {
    guardModelReadyMock.mockResolvedValueOnce(false)
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledWith(false, 'audio')
    expect(submitTaskMock).not.toHaveBeenCalled()
    expect(result).toEqual({})

    w.unmount()
  })

  it('10b. whisper 已下載，vocal_separation=true 但 demucs 未下載 → 第二道 guard 攔截', async () => {
    modelsState.models = [{ family: 'whisper', variant: 'medium', label: 'Medium', size_mb: 1500, downloaded: true, category: 'stt' }]
    guardModelReadyMock.mockResolvedValueOnce(true).mockResolvedValueOnce(false)
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    w.vm.setParams({ ...w.vm.params, vocal_separation: true })
    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenNthCalledWith(1, true, 'audio')
    expect(guardModelReadyMock).toHaveBeenNthCalledWith(2, false, 'audio')
    expect(submitTaskMock).not.toHaveBeenCalled()
    expect(result).toEqual({})

    w.unmount()
  })

  it('10c. translate=true 但翻譯模型未下載 → guardModelReady(false, "llm")（slot=translate→category=llm 既有對照）', async () => {
    modelsState.models = [{ family: 'whisper', variant: 'medium', label: 'Medium', size_mb: 1500, downloaded: true, category: 'stt' }]
    guardModelReadyMock.mockResolvedValueOnce(true).mockResolvedValueOnce(false)
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    w.vm.setParams({ ...w.vm.params, translate: true })
    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenNthCalledWith(2, false, 'llm')
    expect(submitTaskMock).not.toHaveBeenCalled()
    expect(result).toEqual({})

    w.unmount()
  })

  it('10d. summarize=true 但摘要模型未下載 → guardModelReady(false, "llm")（本 task 新補 slot=summarize→category=llm）', async () => {
    modelsState.models = [{ family: 'whisper', variant: 'medium', label: 'Medium', size_mb: 1500, downloaded: true, category: 'stt' }]
    guardModelReadyMock.mockResolvedValueOnce(true).mockResolvedValueOnce(false)
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    w.vm.setParams({ ...w.vm.params, summarize: true })
    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenNthCalledWith(2, false, 'llm')
    expect(submitTaskMock).not.toHaveBeenCalled()
    expect(result).toEqual({})

    w.unmount()
  })

  it('10e. translate=true 且 translate_remote=true → 不追加 translate guard（雲端免下載），只有 whisper 一道', async () => {
    modelsState.models = [{ family: 'whisper', variant: 'medium', label: 'Medium', size_mb: 1500, downloaded: true, category: 'stt' }]
    submitTaskMock.mockResolvedValue('tid-remote')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    w.vm.setParams({ ...w.vm.params, translate: true, translate_remote: true })
    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledTimes(1)
    expect(guardModelReadyMock).toHaveBeenCalledWith(true, 'audio')
    expect(result).toEqual({ task_id: 'tid-remote' })

    w.unmount()
  })

  it('10f. 全部就緒（whisper+demucs+align+translate+summarize 皆已下載/本地）→ execute 正常送出', async () => {
    modelsState.models = [
      { family: 'whisper', variant: 'medium', label: 'Medium', size_mb: 1500, downloaded: true, category: 'stt' },
      { family: 'demucs', variant: 'htdemucs_6s', label: '6-stem', size_mb: 300, downloaded: true, category: 'separate' },
      { family: 'wav2vec2', variant: 'base', label: 'Align', size_mb: 200, downloaded: true, category: 'alignment' },
      { family: 'gemma4', variant: '4b:Q4_K_M', label: 'Gemma4', size_mb: 3000, downloaded: true, category: 'llm' },
    ]
    submitTaskMock.mockResolvedValue('tid-all-ready')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    w.vm.setParams({
      ...w.vm.params,
      vocal_separation: true,
      align: true,
      translate: true,
      translate_model_family: 'gemma4',
      translate_model_size: '4b',
      summarize: true,
      summarize_model_family: 'gemma4',
      summarize_model_size: '4b',
    })
    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledTimes(5)
    expect(result).toEqual({ task_id: 'tid-all-ready' })

    w.unmount()
  })
})
