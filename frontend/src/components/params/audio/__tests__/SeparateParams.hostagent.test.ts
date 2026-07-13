/**
 * ToolParamHost + SeparateParams 合掛整合測（統一參數元件 spec §6；批 3 Task 3.3）。
 * 取代舊 AudioSeparatePanel.agent.test.ts（stub-based，僅測 useAgentPanelHost 契約）——
 * 這裡不 stub 參數元件，PARAM_COMPONENTS['audio.separate'] 是真實 SeparateParams.vue
 * （沿 InterpolateParams.hostagent.test.ts / VolumeParams.hostagent.test.ts 先例）。
 *
 * 例外殼裁決覆核（task 3.3 brief）：舊 panel 有 onTaskComplete（彈窗問跳 MIDI），已上移
 * AudioView（見該檔 askJumpToMidi）——host 端不再有這個掛勾點，本檔只驗證標準 host 契約
 * （agent 欄位縮小為 3 欄、setField/execute/preflight）。AudioView 無既有測試檔（見
 * task brief §5 fallback 條款），askJumpToMidi/handleJumpToMidi 的彈窗邏輯本身未被
 * 這裡覆蓋——僅能靠真機 e2e／既有 AudioView 手動驗收流程涵蓋，記入報告 concerns。
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
  models: [] as Array<{ family: string; variant: string; label: string; downloaded: boolean; category?: string }>,
}))
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({ models: modelsState.models }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
// 靜態 import 讓 SeparateParams.vue 先進 vitest 模組快取（見 CutParams.hostagent.test.ts 同段註記）。
import '@/components/params/audio/SeparateParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'audio.separate',
      panelId: 'audio.separate',
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

describe('SeparateParams × ToolParamHost — agentSchema（stems 縮小：agent 只見 3 欄）', () => {
  it('1. fields=[model_name,output_format,generate_midi]，stems（list）不曝', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const fields = handle.agentSchema.fields
    expect(fields.map((f: any) => f.name)).toEqual(['model_name', 'output_format', 'generate_midi'])

    w.unmount()
  })

  it('2. execute.label=panel.separate.execute；requiresConfirm 退回 host 預設 true（舊 panel 亦為 true）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.separate.execute' })
    w.unmount()
  })
})

describe('SeparateParams × ToolParamHost — setField + getSubmitSpec', () => {
  it('3. setField(output_format, "flac") → getSubmitSpec payload 含新值，不含 file_id', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('output_format', 'flac')).toBe('flac')

    const spec = w.vm.getSubmitSpec()
    expect(spec.apiPath).toBe('/audio/separate')
    expect(spec.payload).toEqual({ model_name: 'htdemucs_6s', output_format: 'flac', generate_midi: false })
    expect(spec.payload).not.toHaveProperty('file_id')
    expect(spec.payload).not.toHaveProperty('stems') // defaults() 未設 stems，params 內無此鍵

    w.unmount()
  })

  it('4. setField(generate_midi, "yes") → coerce boolean', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('generate_midi', 'yes')).toBe(true)

    w.unmount()
  })
})

describe('SeparateParams × ToolParamHost — validate 攔截（stems 空陣列）', () => {
  it('5. params.stems 空陣列（UI 全關 toggle 後） → execute() 不呼叫 submitTask', async () => {
    const w = mountHost()
    await flushPromises()

    w.vm.setParams({ model_name: 'htdemucs_6s', stems: [], output_format: 'wav', generate_midi: false })
    const handle = capturedHandle.current
    const result = await handle.execute()

    expect(submitTaskMock).not.toHaveBeenCalled()
    expect(result).toEqual({})

    w.unmount()
  })
})

describe('SeparateParams × ToolParamHost — execute', () => {
  it('6. execute() → submitTask 打 /audio/separate，payload 含 file_id + model_name/output_format/generate_midi（無 stems，預設全部）', async () => {
    submitTaskMock.mockResolvedValue('tid-separate')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/audio/separate',
      { file_id: 'f1', model_name: 'htdemucs_6s', output_format: 'wav', generate_midi: false },
      'audio.separate.task_label',
      'audio.separate',
      'song.mp3',
    )
    expect(result).toEqual({ task_id: 'tid-separate' })
    expect(w.emitted('submit')).toEqual([['tid-separate']])

    w.unmount()
  })

  it('7. UI 關掉部分 stem toggle 後 execute() → payload 含顯式 stems 陣列', async () => {
    submitTaskMock.mockResolvedValue('tid-partial')
    const w = mountHost()
    await flushPromises()

    // 直接透過 setParams 模擬 UI 互動後的完整陣列寫入（元件行為已由 SeparateParams.test.ts 覆蓋）
    w.vm.setParams({ model_name: 'htdemucs_6s', stems: ['vocals', 'drums'], output_format: 'wav', generate_midi: false })
    const handle = capturedHandle.current

    await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/audio/separate',
      { file_id: 'f1', model_name: 'htdemucs_6s', stems: ['vocals', 'drums'], output_format: 'wav', generate_midi: false },
      'audio.separate.task_label',
      'audio.separate',
      'song.mp3',
    )

    w.unmount()
  })
})

describe('SeparateParams × ToolParamHost — preflight（variant 型 modelRequirement，slot=separate→category=audio）', () => {
  it('8a. modelStore 無對應已下載 demucs variant → guardModelReady(false, "audio")，execute 不送出', async () => {
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

  it('8b. modelStore 有 htdemucs_6s（category=separate, downloaded=true）→ guardModelReady(true, "audio")，execute 正常送出', async () => {
    modelsState.models = [{ family: 'demucs', variant: 'htdemucs_6s', label: '6-stem', downloaded: true, category: 'separate' }]
    submitTaskMock.mockResolvedValue('tid-ok')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledWith(true, 'audio')
    expect(submitTaskMock).toHaveBeenCalled()
    expect(result).toEqual({ task_id: 'tid-ok' })

    w.unmount()
  })
})
