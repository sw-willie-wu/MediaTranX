/**
 * ToolParamHost + LyricsParams 合掛整合測（統一參數元件 spec §6；批 3 Task 3.5——批 3 收官，
 * 照 TranscribeParams.hostagent.test.ts 裁剪）。取代舊 AudioLyricsPanel 直接掛載（無
 * agentSchema/useAgentPanelHost——host 自動曝欄是行為新增，見 lyrics.meta.ts 檔頭差異 5）。
 *
 * 覆蓋：兩 composite 欄位不直曝（agent fields 縮小）、setField 走 composite/一般欄位兩路、
 * execute payload 完整形狀 vs 舊 body 等價、preflight 四道 guard（whisper→demucs(無條件)→
 * align→translate，SLOT_GUARD_CATEGORY 全部既有無需新補）。
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
// 靜態 import 讓 LyricsParams.vue 先進 vitest 模組快取（見 CutParams.hostagent.test.ts 同段註記）。
import '@/components/params/audio/LyricsParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'audio.lyrics',
      panelId: 'audio.lyrics',
      fileId: 'f1',
      currentFileName: 'song.mp3',
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

describe('LyricsParams × ToolParamHost — agentSchema（兩 composite 縮小欄位曝光）', () => {
  it('1. fields = 5 一般欄位（非 covered、非 dict）+ 2 composite（whisper_model/translate_model）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const names = handle.agentSchema.fields.map((f: any) => f.name)
    expect(names).toEqual([
      'output_format', 'translate', 'target_language', 'keep_names', 'translate_style',
      'align',
      'whisper_model', 'translate_model',
    ])
    // 覆蓋欄位（model_size + 七個 translate_*）與 dict 欄位（glossary）不直曝
    expect(names).not.toContain('model_size')
    expect(names).not.toContain('translate_model_family')
    expect(names).not.toContain('glossary')

    w.unmount()
  })

  it('2. execute.label 退回 labelKey（audio.lyrics.task_label）；requiresConfirm 退回 host 預設 true（舊 panel 無 agentSchema）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'audio.lyrics.task_label' })
    w.unmount()
  })
})

describe('LyricsParams × ToolParamHost — setField（composite 路徑 + 一般欄位路徑）', () => {
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

  it('5. setField(whisper_model, "large-v3") → composite 覆蓋 model_size', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('whisper_model', 'large-v3')).toBe('large-v3')
    expect(w.vm.params.model_size).toBe('large-v3')

    w.unmount()
  })
})

describe('LyricsParams × ToolParamHost — execute payload 完整形狀（vs 舊 AudioLyricsPanel body 等價）', () => {
  it('6. 最小狀態（無 translate）→ submitTask 收到 file_id + 基本欄位，無 translate_* 子欄', async () => {
    submitTaskMock.mockResolvedValue('tid-min')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/audio/lyrics',
      {
        file_id: 'f1',
        model_size: 'medium',
        output_format: 'lrc',
        align: false,
        translate: false,
      },
      'audio.lyrics.task_label',
      'audio.lyrics',
      'song.mp3',
    )
    expect(result).toEqual({ task_id: 'tid-min' })
    expect(w.emitted('submit')).toEqual([['tid-min']])

    w.unmount()
  })

  it('7. translate 開（本地模型）→ payload 含完整子欄', async () => {
    submitTaskMock.mockResolvedValue('tid-full')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    w.vm.setParams({
      ...w.vm.params,
      translate: true,
      target_language: 'zh-TW',
      translate_model_family: 'gemma4',
      translate_model_size: '4b',
      translate_quantization: 'Q4_K_M',
      keep_names: false,
      translate_style: 'formal',
    })

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/audio/lyrics',
      expect.objectContaining({
        file_id: 'f1',
        translate: true,
        target_language: 'zh-TW',
        translate_model_family: 'gemma4',
        translate_model_size: '4b',
        translate_quantization: 'Q4_K_M',
        keep_names: false,
        translate_style: 'formal',
      }),
      'audio.lyrics.task_label',
      'audio.lyrics',
      'song.mp3',
    )
    expect(result).toEqual({ task_id: 'tid-full' })

    w.unmount()
  })
})

describe('LyricsParams × ToolParamHost — preflight 四道 guard（whisper→demucs(無條件)→align→translate）', () => {
  it('8a. whisper 模型未下載 → guardModelReady(false, "audio")，execute 不送出', async () => {
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

  it('8b. whisper 已下載但 demucs 未下載（無條件 guard，無需 vocal_separation 開關）→ 第二道 guard 攔截', async () => {
    modelsState.models = [{ family: 'whisper', variant: 'medium', label: 'Medium', size_mb: 1500, downloaded: true, category: 'stt' }]
    guardModelReadyMock.mockResolvedValueOnce(true).mockResolvedValueOnce(false)
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenNthCalledWith(1, true, 'audio')
    expect(guardModelReadyMock).toHaveBeenNthCalledWith(2, false, 'audio')
    expect(submitTaskMock).not.toHaveBeenCalled()
    expect(result).toEqual({})

    w.unmount()
  })

  it('8c. translate=true 但翻譯模型未下載 → guardModelReady(false, "llm")（slot=translate→category=llm 既有對照，無需新補）', async () => {
    modelsState.models = [
      { family: 'whisper', variant: 'medium', label: 'Medium', size_mb: 1500, downloaded: true, category: 'stt' },
      { family: 'demucs', variant: 'htdemucs_6s', label: '6-stem', size_mb: 300, downloaded: true, category: 'separate' },
    ]
    guardModelReadyMock.mockResolvedValueOnce(true).mockResolvedValueOnce(true).mockResolvedValueOnce(false)
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    w.vm.setParams({ ...w.vm.params, translate: true })
    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenNthCalledWith(3, false, 'llm')
    expect(submitTaskMock).not.toHaveBeenCalled()
    expect(result).toEqual({})

    w.unmount()
  })

  it('8d. translate=true 且 translate_remote=true → 不追加 translate guard（雲端免下載），只有 whisper+demucs 兩道', async () => {
    modelsState.models = [
      { family: 'whisper', variant: 'medium', label: 'Medium', size_mb: 1500, downloaded: true, category: 'stt' },
      { family: 'demucs', variant: 'htdemucs_6s', label: '6-stem', size_mb: 300, downloaded: true, category: 'separate' },
    ]
    submitTaskMock.mockResolvedValue('tid-remote')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    w.vm.setParams({ ...w.vm.params, translate: true, translate_remote: true })
    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledTimes(2)
    expect(result).toEqual({ task_id: 'tid-remote' })

    w.unmount()
  })

  it('8e. 全部就緒（whisper+demucs+align+translate 皆已下載/本地）→ execute 正常送出', async () => {
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
      align: true,
      translate: true,
      translate_model_family: 'gemma4',
      translate_model_size: '4b',
    })
    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledTimes(4)
    expect(result).toEqual({ task_id: 'tid-all-ready' })

    w.unmount()
  })
})
