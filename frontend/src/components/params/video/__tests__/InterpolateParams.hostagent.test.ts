/**
 * ToolParamHost + InterpolateParams 合掛整合測（統一參數元件 spec §6；批 2 Task 2.3——
 * host modelRequirement variant 型擴充首用之一）。
 * 仿 TranslateParams.hostagent.test.ts：不 stub 參數元件，PARAM_COMPONENTS['video.interpolate']
 * 是 defineAsyncComponent 懶載真實 InterpolateParams.vue，靜態 import 先進模組快取＋一次
 * flushPromises() 等掛載完成。
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
const ensureLoadedMock = vi.hoisted(() => vi.fn())
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    models: modelsState.models,
    byCategory: (cat: string) => modelsState.models.filter((m) => m.category === cat),
    forPanel: (items: unknown[]) => items,
    ensureLoaded: ensureLoadedMock,
  }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
// 靜態 import 讓 InterpolateParams.vue 先進 vitest 模組快取——見 CutParams.hostagent.test.ts
// 檔頭記載的動態 import race 問題與解法。
import '@/components/params/video/InterpolateParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'video.interpolate',
      panelId: 'video.interpolate',
      fileId: 'f1',
      currentFileName: 'clip.mp4',
      fileInfo: { fps: 30 },
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
  localStorage.clear()
})

describe('InterpolateParams × ToolParamHost — agentSchema 兩層合成', () => {
  it('1. fields 無裸 model 欄位（composite 覆蓋）；有 mode/target_fps/output_format/video_codec', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const fields = handle.agentSchema.fields
    const names = fields.map((f: any) => f.name)
    expect(names).toEqual(expect.arrayContaining(['model', 'mode', 'target_fps', 'output_format', 'video_codec']))
    // composite 的 'model' 覆蓋 schema 的靜態 'model' 欄位——只應出現一次
    expect(names.filter((n: string) => n === 'model')).toHaveLength(1)

    const modelField = fields.find((f: any) => f.name === 'model')
    expect(modelField.type).toBe('enum')
    expect(typeof modelField.options).toBe('function')

    w.unmount()
  })

  it('2. execute.label === panel.interpolate.execute（agentExecuteLabel 選配欄位）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.interpolate.execute' })
    w.unmount()
  })
})

describe('InterpolateParams × ToolParamHost — setField(model, token)', () => {
  it('3. setField(model, "v4.30") → getCurrentValues().model === "v4.30"', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('model', 'v4.30')
    expect(handle.getCurrentValues().model).toBe('v4.30')

    w.unmount()
  })
})

describe('InterpolateParams × ToolParamHost — execute（buildSubmit 剔除 target_fps）', () => {
  it('4a. mode=2x（default）→ submitTask payload 不含 target_fps', async () => {
    submitTaskMock.mockResolvedValue('tid1')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledTimes(1)
    const [apiPath, payload, labelKey, taskType, fileName] = submitTaskMock.mock.calls[0]
    expect(apiPath).toBe('/video/interpolate')
    expect(payload.file_id).toBe('f1')
    expect(payload.mode).toBe('2x')
    expect(payload).not.toHaveProperty('target_fps')
    expect(labelKey).toBe('video.interpolate.task_label')
    expect(taskType).toBe('video.interpolate')
    expect(fileName).toBe('clip.mp4')
    expect(result).toEqual({ task_id: 'tid1' })
    expect(w.emitted('submit')).toEqual([['tid1']])

    w.unmount()
  })

  it('4b. mode=custom → submitTask payload 含 target_fps', async () => {
    submitTaskMock.mockResolvedValue('tid2')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    ;(w.vm as any).setField('mode', 'custom')
    ;(w.vm as any).setField('target_fps', 90)
    await handle.execute()

    const payload = submitTaskMock.mock.calls[0][1]
    expect(payload.mode).toBe('custom')
    expect(payload.target_fps).toBe(90)

    w.unmount()
  })
})

describe('InterpolateParams × ToolParamHost — preflight（variant 型 modelRequirement，slot=interpolate→category=video）', () => {
  it('5a. modelStore 無對應已下載 variant → guardModelReady(false, "video")，execute 不送出', async () => {
    guardModelReadyMock.mockResolvedValueOnce(false)
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledWith(false, 'video')
    expect(submitTaskMock).not.toHaveBeenCalled()
    expect(result).toEqual({})

    w.unmount()
  })

  it('5b. modelStore 有對應已下載 variant（category=interpolate）→ guardModelReady(true, "video")，execute 正常送出', async () => {
    modelsState.models = [{ family: 'rife', variant: 'v4.26', label: 'v4.26', downloaded: true, category: 'interpolate' }]
    submitTaskMock.mockResolvedValue('tid3')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledWith(true, 'video')
    expect(submitTaskMock).toHaveBeenCalled()
    expect(result).toEqual({ task_id: 'tid3' })

    w.unmount()
  })
})
