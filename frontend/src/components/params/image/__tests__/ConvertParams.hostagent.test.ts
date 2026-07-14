/**
 * ToolParamHost + ConvertParams 合掛整合測（統一參數元件 spec §6；批 4 Task 4.1）。
 * 取代舊 ImageConvertPanel.agent.test.ts——host 接手 agent 掛載後，唯一權威測試點；
 * resizeMode 響應式衍生行為已由 ConvertParams.test.ts 覆蓋，本檔專注 host×元件整合
 * （panelId='image.convert' ＝ toolKey/taskType，命名統一小案 Task A 已正名、agentSchema
 * 衍生、execute buildSubmit 互斥清理、outputFormat expose），仿 TranscodeParams.hostagent.test.ts。
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

vi.mock('@/composables/useModelGuard', () => ({
  useModelGuard: () => ({ guardModelReady: vi.fn(async () => true) }),
}))
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({ models: [] }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
import '@/components/params/image/ConvertParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'image.convert',
      // panelId ＝ panelIdFor('image','convert') 自然產出，即 ImageView 掛載時傳入的字面值
      // （命名統一小案 Task A 已正名，與 toolKey/taskType 一致，見 convert.meta.ts 檔頭註解）。
      panelId: 'image.convert',
      fileId: 'f1',
      currentFileName: 'photo.png',
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

describe('ConvertParams × ToolParamHost — agentSchema', () => {
  it('1. panelId="image.convert"；fields 名稱集合 = 後端詞彙全集（schema 順序）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()
    expect(handle.agentSchema.panelId).toBe('image.convert')

    const fields = handle.agentSchema.fields
    expect(fields.map((f: any) => f.name)).toEqual([
      'output_format', 'quality', 'width', 'height', 'scale', 'coalesce',
    ])

    w.unmount()
  })

  it('2. execute.label="panel.transcode.execute"（≠ labelKey "image.convert.task_label"）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.transcode.execute' })

    w.unmount()
  })
})

describe('ConvertParams × ToolParamHost — outputFormat expose（downloadFormatField）', () => {
  it('3. host.outputFormat 反映 params.output_format（預設 png）', async () => {
    const w = mountHost()
    await flushPromises()

    expect(w.vm.outputFormat).toBe('png')

    w.unmount()
  })

  it('4. setField(output_format, "webp") → host.outputFormat 隨之更新', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('output_format', 'webp')
    await flushPromises()

    expect(w.vm.outputFormat).toBe('webp')

    w.unmount()
  })
})

describe('ConvertParams × ToolParamHost — execute（buildSubmit 三態互斥清理）', () => {
  it('5. agent 個別 setField(width)/setField(scale) 留下不一致組合 → execute 送出時 scale 優先、width/height 被剔除', async () => {
    submitTaskMock.mockResolvedValue('tid1')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('width', 800)
    handle.setField('height', 600)
    handle.setField('scale', 150) // 後設 scale——buildSubmit 應以 scale 為準，剔除 width/height

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/image/convert',
      { file_id: 'f1', output_format: 'png', quality: 85, coalesce: false, scale: 150 },
      'image.convert.task_label',
      'image.convert',
      'photo.png',
    )
    expect(result).toEqual({ task_id: 'tid1' })
    expect(w.emitted('submit')).toEqual([['tid1']])

    w.unmount()
  })

  it('6. 未設任何 resize 欄位 → execute payload 不含 width/height/scale', async () => {
    submitTaskMock.mockResolvedValue('tid2')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    await handle.execute()

    const payload = submitTaskMock.mock.calls[0][1]
    expect('width' in payload).toBe(false)
    expect('height' in payload).toBe(false)
    expect('scale' in payload).toBe(false)

    w.unmount()
  })

  it('7. isMultiSelect prop=true → agentSchema handle.isMultiSelect() 回 true', async () => {
    const w = mountHost({ isMultiSelect: true })
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.isMultiSelect()).toBe(true)

    w.unmount()
  })
})
