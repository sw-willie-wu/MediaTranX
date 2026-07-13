/**
 * ToolParamHost + CompressParams 合掛整合測（統一參數元件 spec §6；批 4 Task 4.1）。
 * 取代舊 ImageCompressPanel.agent.test.ts／.render.test.ts——host 接手 agent 掛載後，
 * 唯一權威測試點；palette 動態上限/換圖重置行為已由 CompressParams.test.ts 覆蓋，
 * 本檔專注 host×元件整合（agentSchema 衍生、setField coerce、execute payload、
 * resultMeta attrs fallthrough），仿 CropParams.hostagent.test.ts。
 *
 * 不 stub 參數元件：PARAM_COMPONENTS['image.compress'] 是 defineAsyncComponent 懶載真實
 * CompressParams.vue，mount 後需 flushPromises() 等非同步元件解析完成才有 DOM。
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

// image.compress 無 modelRequirement，preflight 恆 true；掛 mock 只為滿足 ToolParamHost
// 無條件呼叫 useModelStore()/useModelGuard() 不炸 no-active-Pinia（同各批 hostagent 慣例）。
vi.mock('@/composables/useModelGuard', () => ({
  useModelGuard: () => ({ guardModelReady: vi.fn(async () => true) }),
}))
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({ models: [] }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
// 預先靜態 import 讓 CompressParams.vue 先進 vitest 模組快取（見 CutParams.hostagent.test.ts
// 同段註記——動態 import 走 Vite transform pipeline，單一 flushPromises() 攔不住）。
import '@/components/params/image/CompressParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'image.compress',
      panelId: 'image.compress',
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

describe('CompressParams × ToolParamHost — agentSchema', () => {
  it('1. fields 名稱集合 = 後端詞彙全集（schema 順序）；型別衍生正確（gif_frame_drop=number 非 enum、png_lossy=bool 非 png_mode enum）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const fields = handle.agentSchema.fields
    expect(fields.map((f: any) => f.name)).toEqual([
      'strength', 'gif_colors', 'gif_frame_drop', 'gif_optimize_transparency',
      'png_lossy', 'jpeg_progressive', 'jpeg_keep_metadata', 'webp_lossless',
    ])

    const byName = (n: string) => fields.find((f: any) => f.name === n)
    expect(byName('strength').type).toBe('number')
    expect(byName('gif_colors').type).toBe('number')
    expect(byName('gif_frame_drop').type).toBe('number')
    expect(byName('gif_optimize_transparency').type).toBe('bool')
    expect(byName('png_lossy').type).toBe('bool')
    expect(byName('jpeg_progressive').type).toBe('bool')
    expect(byName('jpeg_keep_metadata').type).toBe('bool')
    expect(byName('webp_lossless').type).toBe('bool')

    w.unmount()
  })

  it('2. execute.requiresConfirm=true（預設）；execute.label="panel.compress.execute"（≠ labelKey）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.compress.execute' })

    w.unmount()
  })
})

describe('CompressParams × ToolParamHost — setField coerce（agent 寫入路徑）', () => {
  it('3. setField(strength, "40") → 回 40（number coerce），getCurrentValues().strength === 40', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('strength', '40')).toBe(40)
    expect(handle.getCurrentValues().strength).toBe(40)

    w.unmount()
  })

  it('4. setField(png_lossy, false) → 回 false（boolean coerce）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('png_lossy', false)).toBe(false)
    expect(handle.getCurrentValues().png_lossy).toBe(false)

    w.unmount()
  })
})

describe('CompressParams × ToolParamHost — execute（multiSelect=true）', () => {
  it('5. execute() → submitTask 收到 {file_id,...defaults}，host emit submit', async () => {
    submitTaskMock.mockResolvedValue('tid1')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/image/compress',
      expect.objectContaining({
        file_id: 'f1',
        strength: 75,
        gif_frame_drop: 0,
        gif_optimize_transparency: true,
        png_lossy: true,
        jpeg_progressive: true,
        jpeg_keep_metadata: false,
        webp_lossless: false,
      }),
      'image.compress.task_label',
      'image.compress',
      'photo.png',
    )
    expect(result).toEqual({ task_id: 'tid1' })
    expect(w.emitted('submit')).toEqual([['tid1']])

    w.unmount()
  })

  it('6. isMultiSelect prop=true → agentSchema handle.isMultiSelect() 回 true', async () => {
    const w = mountHost({ isMultiSelect: true })
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.isMultiSelect()).toBe(true)

    w.unmount()
  })
})

describe('CompressParams × ToolParamHost — resultMeta attrs fallthrough（沿 CropParams canvasCropRect 先例）', () => {
  it('7. :result-meta 傳給 <ToolParamHost> → 穿透到 CompressParams，顯示節省摘要', async () => {
    const w = mountHost({ resultMeta: { saved_ratio: 0.42, output_size: 5800, original_size: 10000 } })
    await flushPromises()

    const summary = w.find('.compress-result-summary')
    expect(summary.exists()).toBe(true)
    expect(summary.classes()).toContain('compress-result-saved')
    expect(w.text()).toContain('KB') // sizeInfo（before→after）一併穿透渲染

    w.unmount()
  })
})

describe('CompressParams × ToolParamHost — fileInfo 驅動 palette seed（host watch immediate）', () => {
  it('8. fileInfo 為 GIF＋palette_size=64 → host 掛載後 params.gif_colors 自動 seed 為 64', async () => {
    const w = mountHost({
      fileInfo: { width: 100, height: 100, format: 'GIF', mode: 'P', file_size: 1000, palette_size: 64 },
    })
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.getCurrentValues().gif_colors).toBe(64)

    w.unmount()
  })
})
