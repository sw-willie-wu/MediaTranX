/**
 * ToolParamHost + UpscaleParams 合掛整合測（統一參數元件 spec §6；批 4 Task 4.4）。
 * 仿 EnhanceParams.hostagent.test.ts——覆蓋 agentSchema 兩層合成（雙 composite）、
 * setField 雙 token 展開、execute payload、id 型 modelRequirements 雙道 preflight。
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

interface FakeModel {
  id: string
  family: string
  variant: string
  label: string
  downloaded: boolean
  category?: string
  max_scale?: number
}

const modelsState = vi.hoisted(() => ({ models: [] as FakeModel[] }))
const ensureLoadedMock = vi.hoisted(() => vi.fn())
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    loading: false,
    models: modelsState.models,
    byCategory: (cat: string) => modelsState.models.filter((m) => m.category === cat),
    forPanel: (items: unknown[]) => items,
    ensureLoaded: ensureLoadedMock,
  }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
// 靜態 import 讓 UpscaleParams.vue 先進 vitest 模組快取——見 CutParams.hostagent.test.ts
// 檔頭記載的動態 import race 問題與解法。
import '@/components/params/image/UpscaleParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'image.upscale',
      panelId: 'image.upscale',
      fileId: 'f1',
      currentFileName: 'photo.png',
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

describe('UpscaleParams × ToolParamHost — agentSchema 兩層合成（雙 composite）', () => {
  it('1. fields 無裸 model_id/face_restore_model_id（composite 覆蓋）；有 scale/sharpen/face_fix/face_restore_upscale', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const fields = handle.agentSchema.fields
    const names = fields.map((f: any) => f.name)
    expect(names).not.toContain('model_id')
    expect(names).not.toContain('face_restore_model_id')
    expect(names).toContain('upscale_model')
    expect(names).toContain('face_restore_model')
    expect(names).toEqual(expect.arrayContaining(['scale', 'sharpen', 'face_fix', 'face_restore_upscale']))

    w.unmount()
  })

  it('2. execute.label === panel.upscale.execute（agentExecuteLabel 選配欄位）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.upscale.execute' })
    w.unmount()
  })
})

describe('UpscaleParams × ToolParamHost — setField 雙 token 展開', () => {
  it('3. setField(upscale_model, id) → getParams().model_id 更新', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('upscale_model', 'swinir-lightweight-x4')
    expect((w.vm as any).getParams().model_id).toBe('swinir-lightweight-x4')

    w.unmount()
  })

  it('4. setField(face_restore_model, id) → getParams().face_restore_model_id 更新', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('face_restore_model', 'gfpgan-v1.4')
    expect((w.vm as any).getParams().face_restore_model_id).toBe('gfpgan-v1.4')

    w.unmount()
  })
})

describe('UpscaleParams × ToolParamHost — execute', () => {
  it('5. face_fix=false → submitTask payload 的 face_restore_model_id 為 null（buildSubmit gate）', async () => {
    submitTaskMock.mockResolvedValue('tid1')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledTimes(1)
    const [apiPath, payload, labelKey, taskType, fileName] = submitTaskMock.mock.calls[0]
    expect(apiPath).toBe('/image/upscale')
    expect(payload.file_id).toBe('f1')
    expect(payload.model_id).toBe('realesrgan-x4plus')
    expect(payload.scale).toBe(4)
    expect(payload.face_fix).toBe(false)
    expect(payload.face_restore_model_id).toBeNull()
    expect(labelKey).toBe('image.upscale.task_label')
    expect(taskType).toBe('image.upscale')
    expect(fileName).toBe('photo.png')
    expect(result).toEqual({ task_id: 'tid1' })
    expect(w.emitted('submit')).toEqual([['tid1']])

    w.unmount()
  })
})

describe('UpscaleParams × ToolParamHost — preflight（id 型 modelRequirements，slot=upscale→category=image）', () => {
  it('6a. 主模型未下載 → guardModelReady(false, "image")，execute 不送出', async () => {
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

  it('6b. 主模型已下載（id 相符）→ guardModelReady(true, "image")，execute 正常送出', async () => {
    modelsState.models = [{ id: 'realesrgan-x4plus', family: 'realesrgan', variant: 'x4plus', label: '4x', downloaded: true, category: 'upscale' }]
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

  it('6c. face_fix=true 且已選未下載的 face 模型 → 第二道 guard 觸發（第一道主模型過，第二道 face 卡住）', async () => {
    modelsState.models = [{ id: 'realesrgan-x4plus', family: 'realesrgan', variant: 'x4plus', label: '4x', downloaded: true, category: 'upscale' }]
    guardModelReadyMock.mockResolvedValueOnce(true).mockResolvedValueOnce(false)
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('face_restore_model', 'gfpgan-v1.4')
    ;(w.vm as any).setField('face_fix', true)

    const result = await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledTimes(2)
    expect(guardModelReadyMock).toHaveBeenNthCalledWith(1, true, 'image')
    expect(guardModelReadyMock).toHaveBeenNthCalledWith(2, false, 'image')
    expect(submitTaskMock).not.toHaveBeenCalled()
    expect(result).toEqual({})

    w.unmount()
  })

  it('6d. face_fix=false → 只有一道 guard（不檢查 face 模型即使已選過）', async () => {
    modelsState.models = [{ id: 'realesrgan-x4plus', family: 'realesrgan', variant: 'x4plus', label: '4x', downloaded: true, category: 'upscale' }]
    submitTaskMock.mockResolvedValue('tid3')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('face_restore_model', 'gfpgan-v1.4') // 選過但 face_fix 仍 false

    await handle.execute()

    expect(guardModelReadyMock).toHaveBeenCalledTimes(1)

    w.unmount()
  })
})
