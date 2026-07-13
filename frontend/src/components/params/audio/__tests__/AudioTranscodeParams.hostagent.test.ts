/**
 * ToolParamHost + AudioTranscodeParams 合掛整合測（統一參數元件 spec §6；批 3 Task 3.1）。
 * 取代舊 AudioTranscodePanel.agent.test.ts——host 接手 agent 掛載後，唯一權威測試點；
 * buildSubmit 剔欄邏輯已由 transcode.meta.test.ts 覆蓋，本檔專注 host×元件整合
 * （agentSchema 欄位名＝後端詞彙 audio_bitrate、非舊 agent 名 bitrate／execute 分流／
 * agentRequiresConfirm 預設 true），仿 TranscodeParams.hostagent.test.ts。
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

// audio.transcode 無 modelRequirement，preflight 恆 true；掛 mock 只為滿足 ToolParamHost 無條件
// 呼叫 useModelStore()/useModelGuard() 不炸 no-active-Pinia（沿 TranscodeParams.hostagent.test.ts 慣例）。
vi.mock('@/composables/useModelGuard', () => ({
  useModelGuard: () => ({ guardModelReady: vi.fn(async () => true) }),
}))
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({ models: [] }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
import AppSelect from '@/components/common/AppSelect.vue'
// 預先靜態 import 讓 AudioTranscodeParams.vue 先進 vitest 模組快取（見 CutParams.hostagent.test.ts 同段註記）。
import '@/components/params/audio/AudioTranscodeParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'audio.transcode',
      panelId: 'audio.transcode',
      fileId: 'f1',
      currentFileName: 'clip.mp3',
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
})

describe('AudioTranscodeParams × ToolParamHost — agentSchema', () => {
  it('1. fields 名稱集合＝後端詞彙全集（audio_bitrate，非舊 agent 名 bitrate）；requiresConfirm 預設 true', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const fields = handle.agentSchema.fields
    expect(fields.map((f: any) => f.name)).toEqual([
      'output_format', 'audio_bitrate', 'sample_rate', 'channels',
    ])
    expect(fields.map((f: any) => f.name)).not.toContain('bitrate')

    const byName = (n: string) => fields.find((f: any) => f.name === n)
    expect(byName('output_format').type).toBe('enum')
    expect(byName('output_format').options()).toContain('wma') // schema 全集含 wma（UI 過濾另有測試）
    expect(byName('audio_bitrate').type).toBe('enum')
    expect(byName('sample_rate').type).toBe('number')
    expect(byName('channels').type).toBe('number')
    expect(byName('channels').min).toBe(1)
    expect(byName('channels').max).toBe(2)

    expect(handle.agentSchema.execute.requiresConfirm).toBe(true)
    expect(handle.agentSchema.execute.label).toBe('panel.audio_transcode.execute')

    w.unmount()
  })
})

describe('AudioTranscodeParams × ToolParamHost — setField coerce + getSubmitSpec（agent 寫入路徑）', () => {
  it('2. setField(output_format, "wav") → getSubmitSpec 無損分支剔除 audio_bitrate、無 file_id', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('output_format', 'wav')
    handle.setField('audio_bitrate', '320k')

    const spec = w.vm.getSubmitSpec()
    expect(spec.apiPath).toBe('/audio/transcode')
    expect(spec.payload).toEqual({ output_format: 'wav', sample_rate: null })
    expect(spec.payload).not.toHaveProperty('file_id')

    w.unmount()
  })

  it('3. setField(channels, "2") → coerce 為 number 2，getSubmitSpec 帶入 channels', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('channels', '2')).toBe(2)
    expect(handle.getCurrentValues().channels).toBe(2)

    const spec = w.vm.getSubmitSpec()
    expect(spec.payload.channels).toBe(2)

    w.unmount()
  })
})

describe('AudioTranscodeParams × ToolParamHost — execute', () => {
  it('4. execute() → submitTask 打 /audio/transcode，payload 含 file_id＋預設 output_format=mp3', async () => {
    submitTaskMock.mockResolvedValue('tid-audio')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/audio/transcode',
      { file_id: 'f1', output_format: 'mp3', audio_bitrate: '192k', sample_rate: null },
      'audio.transcode.task_label',
      'audio.transcode',
      'clip.mp3',
    )
    expect(result).toEqual({ task_id: 'tid-audio' })
    expect(w.emitted('submit')).toEqual([['tid-audio']])

    w.unmount()
  })
})

describe('AudioTranscodeParams × ToolParamHost — UI 連動（wma 不入選單，agent 寫入路徑）', () => {
  it('5. agent setField(output_format, "wma") 後，格式 AppSelect 選單裡找不到對應顯示項（UI 過濾，agent 仍可設值）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('output_format', 'wma')
    await flushPromises()

    expect(handle.getCurrentValues().output_format).toBe('wma')
    // AppSelect 顯示的格式選單裡沒有 wma 選項（value 不在展平選項清單裡）
    const formatSelect = w.findComponent(AppSelect)
    const values = (formatSelect.props('options') as Array<{ options: Array<{ value: string }> }>).flatMap(
      (g) => g.options.map((o) => o.value),
    )
    expect(values).not.toContain('wma')

    w.unmount()
  })
})
