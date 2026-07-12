/**
 * ToolParamHost + OcrParams（共用元件）合掛整合測——image.ocr 掛載點（統一參數元件案批 4
 * Task 4.4）。document.ocr 的完整合成/preflight 覆蓋已在
 * document/__tests__/OcrParams.hostagent.test.ts；本檔只驗證 image.ocr 這一側的 registry
 * 註冊正確（toolKey/META/apiPath/agentExecuteLabel 隨掛載點切換）與 execute payload，
 * 避免「兩個 toolKey 共用同一元件」漏掉其中一邊註冊的迴歸。
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

const modelsState = vi.hoisted(() => ({ models: [] as any[] }))
const ensureLoadedMock = vi.hoisted(() => vi.fn())
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    models: modelsState.models,
    byCapability: () => [],
    forPanel: (items: unknown[]) => items,
    ensureLoaded: ensureLoadedMock,
  }),
}))
vi.mock('@/stores/remoteModels', () => ({
  useRemoteModelStore: () => ({ byCapability: () => [], ensureLoaded: vi.fn() }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
import '@/components/params/document/OcrParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'image.ocr',
      panelId: 'image.ocr',
      fileId: 'f1',
      currentFileName: 'photo.png',
      ...props,
    },
    global: { mocks: { $t: (k: string) => k } },
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

describe('image.ocr × ToolParamHost — registry 註冊正確（與 document.ocr 各自獨立 META）', () => {
  it('1. execute.label === panel.ocr.execute（image 專屬，非 document 的 panel.doc_ocr.execute）', async () => {
    const w = mountHost()
    await flushPromises()
    expect(capturedHandle.current.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.ocr.execute' })
    w.unmount()
  })

  it('2. execute() → submitTask apiPath=/image/ocr, taskType=image.ocr, labelKey=image.ocr.task_label', async () => {
    submitTaskMock.mockResolvedValue('tid1')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    await handle.execute()

    const [apiPath, payload, labelKey, taskType] = submitTaskMock.mock.calls[0]
    expect(apiPath).toBe('/image/ocr')
    expect(payload.file_id).toBe('f1')
    expect(labelKey).toBe('image.ocr.task_label')
    expect(taskType).toBe('image.ocr')

    w.unmount()
  })

  it('3. outputFormat expose 對 image.ocr 一樣生效（downloadFormatField 共用同一 meta 工廠）', async () => {
    const w = mountHost()
    await flushPromises()
    expect((w.vm as any).outputFormat).toBe('md')
    w.unmount()
  })
})
