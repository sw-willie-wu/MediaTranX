/**
 * ToolParamHost + TranscodeParams 合掛整合測（統一參數元件 spec §6 / 批 1 Task 1.3）。
 * 取代舊 VideoTranscodePanel.agent.test.ts／.render.test.ts——host 接手 agent 掛載後，
 * 唯一權威測試點；GIF/APNG getParams() 行為已由 transcode.meta.test.ts（buildSubmit/
 * visibleWhen）與 TranscodeParams.test.ts（UI 條件顯示）覆蓋，本檔專注 host×元件整合
 * （agentSchema/setField coerce/execute 分流/UI 連動），仿 CutParams.hostagent.test.ts。
 *
 * 不 stub 參數元件：PARAM_COMPONENTS['video.transcode'] 是 defineAsyncComponent 懶載真實
 * TranscodeParams.vue，mount 後需 flushPromises() 等非同步元件解析完成才有 DOM。
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

// video.transcode 無 modelRequirement，preflight 恆 true；掛 mock 只為滿足 ToolParamHost 現在
// 無條件呼叫 useModelStore()/useModelGuard()（批 1 Task 1.5 host 接線）不炸 no-active-Pinia。
vi.mock('@/composables/useModelGuard', () => ({
  useModelGuard: () => ({ guardModelReady: vi.fn(async () => true) }),
}))
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({ models: [] }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
import AppSelect from '@/components/common/AppSelect.vue'
// 靜態 import 讓 TranscodeParams.vue 先進 vitest 模組快取（同一 resolved path）——
// PARAM_COMPONENTS['video.transcode'] 內部是 defineAsyncComponent(() => import('./video/TranscodeParams.vue'))，
// 若模組尚未快取，動態 import 走 Vite transform pipeline，單一 flushPromises() 攔不住（同
// CutParams.hostagent.test.ts 記載的實測結果）；預先靜態 import 命中同一 cache key 後，
// host 內的動態 import 幾乎同步 resolve，一次 flushPromises() 即可等到渲染完成。
import '@/components/params/video/TranscodeParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'video.transcode',
      panelId: 'video.transcode',
      fileId: 'f1',
      currentFileName: 'clip.mp4',
      fileInfo: null,
      ...props,
    },
    global: {
      mocks: { $t: (k: string) => k },
    },
  })
}

/** AppSelect stub 用 modelValue 反查對應的實例（元件內同時掛多個 AppSelect） */
function findSelectByValue(w: ReturnType<typeof mountHost>, value: unknown) {
  return w.findAllComponents(AppSelect).find((s) => s.props('modelValue') === value)
}

beforeEach(() => {
  submitTaskMock.mockReset()
  isProcessingState.value = false
  capturedHandle.current = null
})

describe('TranscodeParams × ToolParamHost — agentSchema', () => {
  it('1. fields 名稱集合暨型別 = 後端詞彙全集（schema 順序）；crf 有 min/max', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const fields = handle.agentSchema.fields
    expect(fields.map((f: any) => f.name)).toEqual([
      'output_format', 'video_codec', 'crf', 'audio_codec', 'preset',
      'resolution', 'scale_algorithm', 'fps', 'audio_bitrate',
    ])

    const byName = (n: string) => fields.find((f: any) => f.name === n)
    expect(byName('output_format').type).toBe('enum')
    expect(byName('video_codec').type).toBe('enum')
    expect(byName('audio_codec').type).toBe('enum')
    expect(byName('preset').type).toBe('enum')
    expect(byName('resolution').type).toBe('string')
    expect(byName('scale_algorithm').type).toBe('enum')
    expect(byName('audio_bitrate').type).toBe('enum')

    const crfField = byName('crf')
    expect(crfField.type).toBe('number')
    expect(crfField.min).toBe(0)
    expect(crfField.max).toBe(51)

    const fpsField = byName('fps')
    expect(fpsField.type).toBe('number')

    w.unmount()
  })
})

describe('TranscodeParams × ToolParamHost — setField coerce + getSubmitSpec 分流（agent 寫入路徑）', () => {
  it('2. setField(output_format, "mp3") → getCurrentValues 反映；getSubmitSpec 分流到 /video/extract-audio（無 file_id）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('output_format', 'mp3')).toBe('mp3')
    expect(handle.getCurrentValues().output_format).toBe('mp3')

    const spec = w.vm.getSubmitSpec()
    expect(spec.apiPath).toBe('/video/extract-audio')
    expect(spec.payload).toEqual({ audio_format: 'mp3' })
    expect(spec.payload).not.toHaveProperty('file_id')

    w.unmount()
  })

  it('3. setField(output_format, "mp4") → getSubmitSpec 回 /video/transcode', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('output_format', 'mp3') // 先切走，確認 mp4 能切回來
    handle.setField('output_format', 'mp4')

    const spec = w.vm.getSubmitSpec()
    expect(spec.apiPath).toBe('/video/transcode')
    expect(spec.payload).not.toHaveProperty('file_id')

    w.unmount()
  })

  it('4. setField(crf, "30") → coerce 為 number 30', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('crf', '30')).toBe(30)
    expect(handle.getCurrentValues().crf).toBe(30)

    w.unmount()
  })
})

describe('TranscodeParams × ToolParamHost — execute 分流', () => {
  it('5a. output_format=mp4 → submitTask 打 /video/transcode，payload 含 file_id', async () => {
    submitTaskMock.mockResolvedValue('tid-video')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/video/transcode',
      expect.objectContaining({ file_id: 'f1', output_format: 'mp4' }),
      'video.transcode.task_label',
      'video.transcode',
      'clip.mp4',
    )
    expect(result).toEqual({ task_id: 'tid-video' })
    expect(w.emitted('submit')).toEqual([['tid-video']])

    w.unmount()
  })

  it('5b. output_format=mp3（分流）→ submitTask 打 /video/extract-audio，payload 含 file_id 無視訊欄位', async () => {
    submitTaskMock.mockResolvedValue('tid-audio')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('output_format', 'mp3')
    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/video/extract-audio',
      { file_id: 'f1', audio_format: 'mp3' },
      'video.transcode.extract_audio',
      'video.extract_audio',
      'clip.mp4',
    )
    expect(result).toEqual({ task_id: 'tid-audio' })
    expect(w.emitted('submit')).toEqual([['tid-audio']])

    w.unmount()
  })
})

describe('TranscodeParams × ToolParamHost — UI 連動（resolution 響應式衍生，agent 寫入路徑）', () => {
  it('6a. agent setField(resolution, "1920x1080") 後，AppSelect 顯示 1080p 預設清單值（非 custom 模式）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('resolution', '1920x1080')
    await flushPromises()

    const resolutionSelect = findSelectByValue(w, '1920x1080')
    expect(resolutionSelect).toBeTruthy()
    expect(resolutionSelect!.find('.app-select-value').text()).toContain('1080p')
    expect(w.find('.size-inputs').exists()).toBe(false)

    w.unmount()
  })

  it('6b. agent setField(resolution, "999x777")（非預設清單值）→ 元件反推 custom 模式，寬高輸入框顯示 999/777', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('resolution', '999x777')
    await flushPromises()

    expect(w.find('.size-inputs').exists()).toBe(true)
    const inputs = w.findAll('.size-inputs input[type="number"]')
    expect(inputs[0].element.value).toBe('999')
    expect(inputs[1].element.value).toBe('777')

    // custom 模式下 resolution AppSelect 顯示「自訂」選項（value: 'custom'）
    const customSelect = findSelectByValue(w, 'custom')
    expect(customSelect).toBeTruthy()

    w.unmount()
  })
})
