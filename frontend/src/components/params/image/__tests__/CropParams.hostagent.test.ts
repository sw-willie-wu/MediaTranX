/**
 * ToolParamHost + ImageCropParams 合掛整合測（統一參數元件 spec §6；批 4 Task 4.3）。
 * 沿 video/__tests__/CropParams.hostagent.test.ts 慣例：不 stub 參數元件，真實走
 * defineAsyncComponent 懶載。
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

// image.crop 無 modelRequirement，preflight 恆 true；掛 mock 只為滿足 ToolParamHost 無條件呼叫
// useModelStore()/useModelGuard() 不炸 no-active-Pinia（同 video CropParams.hostagent.test.ts 慣例）。
vi.mock('@/composables/useModelGuard', () => ({
  useModelGuard: () => ({ guardModelReady: vi.fn(async () => true) }),
}))
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({ models: [] }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
// 預先靜態 import 讓 CropParams.vue 先進 vitest 模組快取（見 video CropParams.hostagent.test.ts 同段註記）。
import '@/components/params/image/CropParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'image.crop',
      panelId: 'image.crop',
      fileId: 'f1',
      currentFileName: 'photo.png',
      fileInfo: { width: 1920, height: 1080 },
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

describe('ImageCropParams × ToolParamHost — agentSchema', () => {
  it('1. fields 名稱集合＝後端詞彙 x/y/width/height，皆 number 型別（批 4 新增 agent 能力）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const fields = handle.agentSchema.fields
    expect(fields.map((f: any) => f.name)).toEqual(['x', 'y', 'width', 'height'])
    for (const f of fields) expect(f.type).toBe('number')

    w.unmount()
  })

  it('2. execute.requiresConfirm=true（預設）；execute.label 退回 meta.labelKey（未設 agentExecuteLabel）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'image.crop.task_label' })

    w.unmount()
  })
})

describe('ImageCropParams × ToolParamHost — setField coerce（agent 寫入路徑）', () => {
  it('3. setField(width, "640") → 回 640，getCurrentValues().width === 640（number coerce）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('width', '640')).toBe(640)
    expect(handle.getCurrentValues().width).toBe(640)

    w.unmount()
  })
})

describe('ImageCropParams × ToolParamHost — execute', () => {
  it('4. validate 擋 width/height 未填 → submitTask 不被呼叫', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    await handle.execute()
    expect(submitTaskMock).not.toHaveBeenCalled()

    w.unmount()
  })

  it('5. width/height 皆填 → execute() submitTask 收到 {file_id,x,y,width,height}，host emit submit', async () => {
    submitTaskMock.mockResolvedValue('tid1')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('width', 640)
    handle.setField('height', 480)
    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/image/crop',
      { file_id: 'f1', x: 0, y: 0, width: 640, height: 480 },
      'image.crop.task_label',
      'image.crop',
      'photo.png',
    )
    expect(result).toEqual({ task_id: 'tid1' })
    expect(w.emitted('submit')).toEqual([['tid1']])

    w.unmount()
  })
})

describe('ImageCropParams × ToolParamHost — 單根元件 attrs fallthrough（crop 專屬 prop/事件）', () => {
  it('6. :canvas-crop-rect 傳給 <ToolParamHost> → 穿透到 CropParams，驅動 setField 等價的 params 更新', async () => {
    // canvasCropRect 的 watch 非 immediate（鏡射舊 panel：只在「拖曳變化」時才寫回,
    // 掛載當下有值不算變化）,故先以 null 掛載,再 setProps 觸發變化,驗證 attrs
    // fallthrough 是響應式穿透(非僅初始 props 複製一次)。
    const w = mountHost({ canvasCropRect: null })
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle.getCurrentValues()).toEqual({ x: 0, y: 0, width: undefined, height: undefined })

    await w.setProps({ canvasCropRect: { x: 10.4, y: 20.6, w: 100.5, h: 50.2 } })
    await flushPromises()

    expect(handle.getCurrentValues()).toEqual({ x: 10, y: 21, width: 101, height: 50 })

    w.unmount()
  })

  it('7. @update:show-crop-overlay 掛在 <ToolParamHost> → CropParams 掛載 immediate emit 穿透到父層', async () => {
    const onShowCropOverlay = vi.fn()
    const w = mount(ToolParamHost, {
      props: {
        toolKey: 'image.crop',
        panelId: 'image.crop',
        fileId: 'f1',
        currentFileName: 'photo.png',
        fileInfo: { width: 1920, height: 1080 },
        'onUpdate:showCropOverlay': onShowCropOverlay,
      },
      global: {
        mocks: { $t: (k: string) => k },
      },
    })
    await flushPromises()

    expect(onShowCropOverlay).toHaveBeenCalledWith(true)

    w.unmount()
  })

  it('8. @update:aspect-ratio 掛在 <ToolParamHost> → CropParams 選長寬比後穿透到父層', async () => {
    const onAspectRatio = vi.fn()
    const w = mount(ToolParamHost, {
      props: {
        toolKey: 'image.crop',
        panelId: 'image.crop',
        fileId: 'f1',
        currentFileName: 'photo.png',
        fileInfo: { width: 1920, height: 1080 },
        'onUpdate:aspectRatio': onAspectRatio,
      },
      global: {
        mocks: { $t: (k: string) => k },
      },
    })
    await flushPromises()

    const AppSelect = (await import('@/components/common/AppSelect.vue')).default
    const select = w.findComponent(AppSelect)
    select.vm.$emit('update:modelValue', '16:9')
    await flushPromises()

    expect(onAspectRatio).toHaveBeenCalledWith('16:9')

    w.unmount()
  })
})
