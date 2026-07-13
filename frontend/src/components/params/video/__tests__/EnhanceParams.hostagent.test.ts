/**
 * ToolParamHost + EnhanceParams 合掛整合測（統一參數元件 spec §6；批 2 Task 2.3——
 * host modelRequirement variant 型擴充首用之一，另 family 過濾路徑）。
 * 仿 InterpolateParams.hostagent.test.ts。
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
  models: [] as Array<{ family: string; variant: string; label: string; downloaded: boolean; category?: string; subcategory?: string }>,
}))
const ensureLoadedMock = vi.hoisted(() => vi.fn())
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    models: modelsState.models,
    byCategory: (cat: string) => modelsState.models.filter((m) => m.category === cat || m.subcategory === cat),
    forPanel: (items: unknown[]) => items,
    ensureLoaded: ensureLoadedMock,
  }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
// 靜態 import 讓 EnhanceParams.vue 先進 vitest 模組快取——見 CutParams.hostagent.test.ts
// 檔頭記載的動態 import race 問題與解法。
import '@/components/params/video/EnhanceParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'video.enhance',
      panelId: 'video.enhance',
      fileId: 'f1',
      currentFileName: 'clip.mp4',
      fileInfo: { width: 640, height: 480 },
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

describe('EnhanceParams × ToolParamHost — agentSchema 兩層合成', () => {
  it('1. fields 無裸 variant 欄位（composite 覆蓋為 model）；有 output_format/video_codec', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const fields = handle.agentSchema.fields
    const names = fields.map((f: any) => f.name)
    expect(names).not.toContain('variant')
    expect(names).toContain('model')
    expect(names).toEqual(expect.arrayContaining(['output_format', 'video_codec']))
    expect(names.filter((n: string) => n === 'model')).toHaveLength(1)

    const modelField = fields.find((f: any) => f.name === 'model')
    expect(modelField.type).toBe('enum')
    expect(typeof modelField.options).toBe('function')

    w.unmount()
  })

  it('2. execute.label === panel.enhance.execute（agentExecuteLabel 選配欄位）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.enhance.execute' })
    w.unmount()
  })
})

describe('EnhanceParams × ToolParamHost — setField(model, token) → variant+model 展開', () => {
  it('3. setField(model, "animevideov3") → getCurrentValues：composite 值反映新 variant，params.variant/model 同步更新', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('model', 'animevideov3')
    expect(handle.getCurrentValues().model).toBe('animevideov3')
    expect((w.vm as any).getParams().variant).toBe('animevideov3')
    expect((w.vm as any).getParams().model).toBe('realesrgan')

    w.unmount()
  })
})

describe('EnhanceParams × ToolParamHost — execute', () => {
  it('4. execute() → submitTask 收到 {file_id, model, variant, output_format, video_codec}', async () => {
    submitTaskMock.mockResolvedValue('tid1')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledTimes(1)
    const [apiPath, payload, labelKey, taskType, fileName] = submitTaskMock.mock.calls[0]
    expect(apiPath).toBe('/video/enhance')
    expect(payload.file_id).toBe('f1')
    expect(payload.model).toBe('realesrgan')
    expect(payload.variant).toBe('x4plus')
    expect(payload.output_format).toBe('mp4')
    expect(payload.video_codec).toBe('h264')
    expect(labelKey).toBe('video.enhance.task_label')
    expect(taskType).toBe('video.enhance')
    expect(fileName).toBe('clip.mp4')
    expect(result).toEqual({ task_id: 'tid1' })
    expect(w.emitted('submit')).toEqual([['tid1']])

    w.unmount()
  })
})

describe('EnhanceParams × ToolParamHost — preflight（variant 型 modelRequirement + family 過濾，slot=enhance→category=image）', () => {
  it('5a. modelStore 無對應已下載 variant → guardModelReady(false, "image")，execute 不送出', async () => {
    guardModelReadyMock.mockResolvedValueOnce(false)
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledWith(false, 'image')
    expect(submitTaskMock).not.toHaveBeenCalled()
    expect(result).toEqual({})

    w.unmount()
  })

  it('5b. modelStore 有對應已下載 variant（family=realesrgan, category=upscale）→ guardModelReady(true, "image")，execute 正常送出', async () => {
    modelsState.models = [{ family: 'realesrgan', variant: 'x4plus', label: '4x', downloaded: true, category: 'upscale' }]
    submitTaskMock.mockResolvedValue('tid2')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledWith(true, 'image')
    expect(submitTaskMock).toHaveBeenCalled()
    expect(result).toEqual({ task_id: 'tid2' })

    w.unmount()
  })

  it('5c. modelStore 有相同 variant 但 family 不符（非 realesrgan）→ guardModelReady(false, "image")', async () => {
    modelsState.models = [{ family: 'swinir', variant: 'x4plus', label: '4x', downloaded: true, category: 'upscale' }]
    guardModelReadyMock.mockResolvedValueOnce(false)
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledWith(false, 'image')

    w.unmount()
  })
})
