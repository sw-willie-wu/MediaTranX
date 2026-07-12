/**
 * ToolParamHost + CutParams 合掛整合測（統一參數元件 spec §6 / Task 0.8）。
 * 取代舊 VideoCutPanel.agent.test.ts——host 接手 agent 掛載後，唯一權威測試點。
 * 不 stub 參數元件：PARAM_COMPONENTS['video.cut'] 是 defineAsyncComponent 懶載真實
 * CutParams.vue，mount 後需 flushPromises() 等非同步元件解析完成才有 DOM。
 * mock 策略沿用 ToolParamHost.test.ts：useSubmitTask（spy submitTask）＋
 * useAgentPanelHost（攔 handle，不經真實 panelRegistry——與 host 單元測一致）。
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

import ToolParamHost from '@/components/params/ToolParamHost.vue'
// 靜態 import 讓 CutParams.vue 先進 vitest 模組快取（同一 resolved path）——
// PARAM_COMPONENTS['video.cut'] 內部是 defineAsyncComponent(() => import('./video/CutParams.vue'))，
// 若模組尚未快取，動態 import 走 Vite transform pipeline，單一 flushPromises() 攔不住（實測會卡在
// pending，wrapper.html() 恆為空字串）；預先靜態 import 命中同一 cache key 後，host 內的動態 import
// 幾乎同步 resolve，一次 flushPromises() 即可等到渲染完成。
import '@/components/params/video/CutParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'video.cut',
      panelId: 'video.cut',
      fileId: 'f1',
      currentFileName: 'clip.mp4',
      fileInfo: { duration: 120 }, // seedOnFileChange → start_time:0, end_time:120
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

describe('CutParams × ToolParamHost — agentSchema', () => {
  it('1. fields 名稱集合＝後端詞彙 start_time/end_time/stream_copy；start/end 為 number+seconds description', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const fields = handle.agentSchema.fields
    expect(fields.map((f: any) => f.name)).toEqual(['start_time', 'end_time', 'stream_copy'])

    const startField = fields.find((f: any) => f.name === 'start_time')
    const endField = fields.find((f: any) => f.name === 'end_time')
    const streamCopyField = fields.find((f: any) => f.name === 'stream_copy')
    expect(startField.type).toBe('number')
    expect(startField.description).toBe('seconds')
    expect(endField.type).toBe('number')
    expect(endField.description).toBe('seconds')
    expect(streamCopyField.type).toBe('bool')

    w.unmount()
  })
})

describe('CutParams × ToolParamHost — setField coerce（agent 寫入路徑）', () => {
  it('2. setField(start_time, "90") → 回 90，getCurrentValues().start_time === 90（number coerce）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('start_time', '90')).toBe(90)
    expect(handle.getCurrentValues().start_time).toBe(90)

    w.unmount()
  })

  it('3. setField(stream_copy, false) → getCurrentValues 反映', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('stream_copy', false)).toBe(false)
    expect(handle.getCurrentValues().stream_copy).toBe(false)

    w.unmount()
  })
})

describe('CutParams × ToolParamHost — execute', () => {
  it('4. execute() → submitTask 收到 {file_id, start_time, end_time, stream_copy}，host emit submit', async () => {
    submitTaskMock.mockResolvedValue('tid1')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/video/cut',
      { file_id: 'f1', start_time: 0, end_time: 120, stream_copy: true },
      'video.cut.task_label',
      'video.cut',
      'clip.mp4',
    )
    expect(result).toEqual({ task_id: 'tid1' })
    expect(w.emitted('submit')).toEqual([['tid1']])

    w.unmount()
  })
})

describe('CutParams × ToolParamHost — UI 連動（批 0 全鏈關鍵驗證）', () => {
  it('5. agent setField(start_time, 90) 後，CutParams 輸入框顯示重推為 00:01:30', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('start_time', 90)
    await flushPromises()

    const startInput = w.findAll('input[type="text"]')[0]
    expect(startInput.element.value).toBe('00:01:30')

    w.unmount()
  })
})

describe('CutParams × ToolParamHost — expose.params 解包行為', () => {
  it('6. w.vm.params 是自動解包後的 plain object（非 Ref），VideoView 橋接 cutPanelRef.value.params.start_time 可直讀', async () => {
    const w = mountHost()
    await flushPromises()

    // defineExpose 曝露的 ref 屬性經 Vue 公開實例自動解包（同 VideoView.vue 橋接 computed 假設）。
    const exposedParams = (w.vm as any).params
    expect(exposedParams).not.toHaveProperty('value') // 不是 Ref wrapper
    expect(exposedParams.start_time).toBe(0)
    expect(exposedParams.end_time).toBe(120)

    w.unmount()
  })
})
