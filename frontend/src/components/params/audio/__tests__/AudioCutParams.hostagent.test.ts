/**
 * ToolParamHost + AudioCutParams 合掛整合測（統一參數元件 spec §6；批 3 Task 3.2）。
 * 取代舊 AudioCutPanel（無 agent test 可遷——舊無 agentSchema）；新增 hostagent 整合測
 * 斷言 agent 欄位 start_time/end_time＋setField 寫入，以及 host.notify('trimRange', …)
 * 轉呼／update:trimRange 經單根元件 attrs fallthrough 穿透（沿 CutParams.hostagent.test.ts、
 * VolumeParams.hostagent.test.ts 先例）。
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

// audio.cut 無 modelRequirement，preflight 恆 true；掛 mock 只為滿足 ToolParamHost 無條件
// 呼叫 useModelStore()/useModelGuard() 不炸 no-active-Pinia（沿 CutParams.hostagent.test.ts 慣例）。
vi.mock('@/composables/useModelGuard', () => ({
  useModelGuard: () => ({ guardModelReady: vi.fn(async () => true) }),
}))
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({ models: [] }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
// 靜態 import 讓 AudioCutParams.vue 先進 vitest 模組快取（見 CutParams.hostagent.test.ts 同段註記）。
import '@/components/params/audio/AudioCutParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'audio.cut',
      panelId: 'audio.cut',
      fileId: 'f1',
      currentFileName: 'clip.mp3',
      fileInfo: { duration: 100 }, // seedOnFileChange → start=00:00:20, end=00:01:20
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

describe('AudioCutParams × ToolParamHost — agentSchema', () => {
  it('1. fields 名稱集合＝start_time/end_time；type=string，agentHint=HH:MM:SS；requiresConfirm 預設 true', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const fields = handle.agentSchema.fields
    expect(fields.map((f: any) => f.name)).toEqual(['start_time', 'end_time'])

    const startField = fields.find((f: any) => f.name === 'start_time')
    const endField = fields.find((f: any) => f.name === 'end_time')
    expect(startField.type).toBe('string')
    expect(startField.description).toBe('HH:MM:SS')
    expect(endField.type).toBe('string')
    expect(endField.description).toBe('HH:MM:SS')

    // 舊 panel 無 agentSchema——host 自動曝欄位是行為新增；requiresConfirm/label 退回預設
    expect(handle.agentSchema.execute.requiresConfirm).toBe(true)
    expect(handle.agentSchema.execute.label).toBe('audio.cut.task_label')

    w.unmount()
  })
})

describe('AudioCutParams × ToolParamHost — seedOnFileChange', () => {
  it('2. fileInfo.duration=100 → params 初值 start=00:00:20/end=00:01:20', async () => {
    const w = mountHost()
    await flushPromises()
    expect((w.vm as any).params).toEqual({ start_time: '00:00:20', end_time: '00:01:20' })
    w.unmount()
  })
})

describe('AudioCutParams × ToolParamHost — setField（agent 寫入路徑）', () => {
  it('3. setField(start_time, "00:05:00") → 直寫字串，getCurrentValues 反映', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('start_time', '00:05:00')).toBe('00:05:00')
    expect(handle.getCurrentValues().start_time).toBe('00:05:00')

    w.unmount()
  })

  it('4. setField(end_time, "00:10:00") → getSubmitSpec 帶入正確 payload、不含 file_id', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('end_time', '00:10:00')
    const spec = w.vm.getSubmitSpec()
    expect(spec.apiPath).toBe('/audio/cut')
    expect(spec.payload).toEqual({ start_time: '00:00:20', end_time: '00:10:00' })
    expect(spec.payload).not.toHaveProperty('file_id')

    w.unmount()
  })
})

describe('AudioCutParams × ToolParamHost — validate 攔截', () => {
  it('5. end<=start → execute() 不呼叫 submitTask（validate 擋下）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('start_time', '00:05:00')
    handle.setField('end_time', '00:01:00')

    const result = await handle.execute()
    expect(submitTaskMock).not.toHaveBeenCalled()
    expect(result).toEqual({})

    w.unmount()
  })
})

describe('AudioCutParams × ToolParamHost — execute', () => {
  it('6. execute() → submitTask 打 /audio/cut，payload 含 file_id + start_time/end_time', async () => {
    submitTaskMock.mockResolvedValue('tid-cut')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/audio/cut',
      { file_id: 'f1', start_time: '00:00:20', end_time: '00:01:20' },
      'audio.cut.task_label',
      'audio.cut',
      'clip.mp3',
    )
    expect(result).toEqual({ task_id: 'tid-cut' })
    expect(w.emitted('submit')).toEqual([['tid-cut']])

    w.unmount()
  })
})

describe('AudioCutParams × ToolParamHost — trim 三角橋接（host notify 通道首用）', () => {
  it('7. mount 時（seed 完成後）經單根元件 attrs fallthrough 穿透初始比例 update:trimRange', async () => {
    const onTrimRange = vi.fn()
    const w = mount(ToolParamHost, {
      props: {
        toolKey: 'audio.cut',
        panelId: 'audio.cut',
        fileId: 'f1',
        currentFileName: 'clip.mp3',
        fileInfo: { duration: 100 },
        'onUpdate:trimRange': onTrimRange,
      },
      global: {
        mocks: { $t: (k: string) => k },
      },
    })
    await flushPromises()

    expect(onTrimRange).toHaveBeenCalledWith({ start: 0.2, end: 0.8 })

    w.unmount()
  })

  it('8. host.notify(\'trimRange\', ratio) 轉呼參數元件，params 換算寫回 HH:MM:SS', async () => {
    const w = mountHost()
    await flushPromises()

    ;(w.vm as any).notify('trimRange', { start: 0.1, end: 0.9 })
    await flushPromises()

    expect((w.vm as any).params).toEqual({ start_time: '00:00:10', end_time: '00:01:30' })

    w.unmount()
  })

  it('9. agent setField 改 start_time/end_time → attrs fallthrough 再收到新的 update:trimRange 比例', async () => {
    const onTrimRange = vi.fn()
    const w = mount(ToolParamHost, {
      props: {
        toolKey: 'audio.cut',
        panelId: 'audio.cut',
        fileId: 'f1',
        currentFileName: 'clip.mp3',
        fileInfo: { duration: 100 },
        'onUpdate:trimRange': onTrimRange,
      },
      global: {
        mocks: { $t: (k: string) => k },
      },
    })
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('start_time', '00:00:10')
    handle.setField('end_time', '00:00:90')
    await flushPromises()

    expect(onTrimRange).toHaveBeenLastCalledWith({ start: 0.1, end: 0.9 })

    w.unmount()
  })

  it('10. 回歸：notify(trimRange) 寫回 params 後不應再多發 update:trimRange echo（_skipOutbound 抑制入向後的出向反射）', async () => {
    const onTrimRange = vi.fn()
    const w = mount(ToolParamHost, {
      props: {
        toolKey: 'audio.cut',
        panelId: 'audio.cut',
        fileId: 'f1',
        currentFileName: 'clip.mp3',
        fileInfo: { duration: 100 },
        'onUpdate:trimRange': onTrimRange,
      },
      global: {
        mocks: { $t: (k: string) => k },
      },
    })
    await flushPromises()
    // 掛載期（seedOnFileChange＋immediate watch）已產生一次初始 update:trimRange（見 test 7），
    // 這裡只記錄基準數，之後斷言 notify() 不再新增。
    const seedCallCount = onTrimRange.mock.calls.length

    // start=0.234 floor 後對應到 23/100=0.23——與入向 ratio 不同，若 outbound echo 未被抑制，
    // watch(props.params) 會用這個「被地板化過」的新 ratio 再 emit 一次，造成波形 handle 跳動。
    ;(w.vm as any).notify('trimRange', { start: 0.234, end: 0.9 })
    await flushPromises()

    expect((w.vm as any).params).toEqual({ start_time: '00:00:23', end_time: '00:01:30' })
    expect(onTrimRange.mock.calls.length).toBe(seedCallCount)

    w.unmount()
  })
})
