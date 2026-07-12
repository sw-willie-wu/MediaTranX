/**
 * ToolParamHost + FilterParams 合掛整合測（統一參數元件 spec §6；批 4 Task 4.2 ⭐合併 task）。
 * 取代舊 ImageAdjustPanel.agent.test.ts／ImageFilterPanel.agent.test.ts——host 接手 agent
 * 掛載後，唯一權威測試點。同 tool-key 'image.filter' 雙掛載（panelId 'image.adjust'/
 * 'image.filter'），驗證：雙 panelId 各自獨立註冊、agentSchema.fields 皆為合併後 11 欄
 * （曝露面變化，見 filter.meta.ts 檔頭）、requiresConfirm=false、labelKey 覆蓋讓 adjust 掛載點
 * 的任務顯示名稱正確（image.adjust.task_label），execute() 皆打同一 /image/filter。
 *
 * 批 4 Task 4.2 review 修復：agent-execute-label prop 覆蓋讓兩 panelId 的 agent 執行標籤
 * 各自復原舊 per-panel 值 'panel.adjust.execute'/'panel.filter.execute'（見 4b）。
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

const handles = vi.hoisted(() => ({ byPanelId: new Map<string, any>() }))
vi.mock('@/composables/useAgentPanelHost', () => ({
  useAgentPanelHost: (panelId: string, handle: any) => {
    handles.byPanelId.set(panelId, handle)
  },
}))

vi.mock('@/composables/useModelGuard', () => ({
  useModelGuard: () => ({ guardModelReady: vi.fn(async () => true) }),
}))
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({ models: [] }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
import AppRange from '@/components/common/AppRange.vue'
import '@/components/params/image/FilterParams.vue'

function mountAdjustHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'image.filter',
      panelId: 'image.adjust',
      labelKey: 'image.adjust.task_label',
      agentExecuteLabel: 'panel.adjust.execute',
      fileId: 'f1',
      currentFileName: 'photo.png',
      fileInfo: null,
      ...props,
    },
    attrs: { 'field-group': 'adjust' },
    global: { mocks: { $t: (k: string) => k } },
  })
}

function mountFilterHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'image.filter',
      panelId: 'image.filter',
      agentExecuteLabel: 'panel.filter.execute',
      fileId: 'f1',
      currentFileName: 'photo.png',
      fileInfo: null,
      ...props,
    },
    attrs: { 'field-group': 'filter' },
    global: { mocks: { $t: (k: string) => k } },
  })
}

beforeEach(() => {
  submitTaskMock.mockReset()
  isProcessingState.value = false
  handles.byPanelId.clear()
})

describe('FilterParams × ToolParamHost — 雙 panelId 各自獨立註冊', () => {
  it('1. adjust/filter 兩掛載點各自以自己的 panelId 註冊 handle（互不覆蓋）', async () => {
    const wAdjust = mountAdjustHost()
    const wFilter = mountFilterHost()
    await flushPromises()

    expect(handles.byPanelId.get('image.adjust')).toBeTruthy()
    expect(handles.byPanelId.get('image.filter')).toBeTruthy()
    expect(handles.byPanelId.get('image.adjust')).not.toBe(handles.byPanelId.get('image.filter'))

    wAdjust.unmount()
    wFilter.unmount()
  })
})

describe('FilterParams × ToolParamHost — agentSchema（合併後曝露面＝兩 panelId 皆見 11 欄）', () => {
  it('2. adjust panelId 的 agentSchema.fields 為 11 欄全集（非舊 6 欄），順序＝meta.schema', async () => {
    const w = mountAdjustHost()
    await flushPromises()
    const handle = handles.byPanelId.get('image.adjust')

    expect(handle.agentSchema.panelId).toBe('image.adjust')
    expect(handle.agentSchema.fields.map((f: any) => f.name)).toEqual([
      'brightness', 'contrast', 'saturation', 'hue', 'sharpness', 'warmth',
      'grayscale', 'sepia', 'invert', 'blur', 'vignette',
    ])

    w.unmount()
  })

  it('3. filter panelId 的 agentSchema.fields 同為 11 欄全集', async () => {
    const w = mountFilterHost()
    await flushPromises()
    const handle = handles.byPanelId.get('image.filter')

    expect(handle.agentSchema.panelId).toBe('image.filter')
    expect(handle.agentSchema.fields).toHaveLength(11)

    w.unmount()
  })

  it('4. 兩 panelId 的 execute.requiresConfirm 皆為 false（沿 meta.agentRequiresConfirm）', async () => {
    const wAdjust = mountAdjustHost()
    const wFilter = mountFilterHost()
    await flushPromises()

    expect(handles.byPanelId.get('image.adjust').agentSchema.execute.requiresConfirm).toBe(false)
    expect(handles.byPanelId.get('image.filter').agentSchema.execute.requiresConfirm).toBe(false)

    wAdjust.unmount()
    wFilter.unmount()
  })

  it('4b. 兩 panelId 的 execute.label 各自復原舊 per-panel 標籤（agent-execute-label prop 覆蓋，批 4 Task 4.2 修復）', async () => {
    const wAdjust = mountAdjustHost()
    const wFilter = mountFilterHost()
    await flushPromises()

    expect(handles.byPanelId.get('image.adjust').agentSchema.execute.label).toBe('panel.adjust.execute')
    expect(handles.byPanelId.get('image.filter').agentSchema.execute.label).toBe('panel.filter.execute')

    wAdjust.unmount()
    wFilter.unmount()
  })
})

describe('FilterParams × ToolParamHost — labelKey 覆蓋（批次/單筆任務顯示名稱）', () => {
  it('5. adjust host 的 getSubmitSpec().labelKey = "image.adjust.task_label"（props 覆蓋）', async () => {
    const w = mountAdjustHost()
    await flushPromises()
    const spec = (w.vm as any).getSubmitSpec()
    expect(spec.labelKey).toBe('image.adjust.task_label')
    expect(spec.apiPath).toBe('/image/filter')
    expect(spec.taskType).toBe('image.filter')

    w.unmount()
  })

  it('6. filter host 未傳 labelKey → getSubmitSpec().labelKey 沿 meta.labelKey "image.filter.task_label"', async () => {
    const w = mountFilterHost()
    await flushPromises()
    const spec = (w.vm as any).getSubmitSpec()
    expect(spec.labelKey).toBe('image.filter.task_label')

    w.unmount()
  })
})

describe('FilterParams × ToolParamHost — execute 皆打同一 /image/filter', () => {
  it('7. adjust host execute() → submitTask 第一參數 apiPath="/image/filter"，label="image.adjust.task_label"', async () => {
    submitTaskMock.mockResolvedValue('tid-adjust')
    const w = mountAdjustHost()
    await flushPromises()

    await (w.vm as any).execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/image/filter',
      expect.objectContaining({ file_id: 'f1' }),
      'image.adjust.task_label',
      'image.filter',
      'photo.png',
    )

    w.unmount()
  })

  it('8. filter host execute() → submitTask label="image.filter.task_label"', async () => {
    submitTaskMock.mockResolvedValue('tid-filter')
    const w = mountFilterHost()
    await flushPromises()

    await (w.vm as any).execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/image/filter',
      expect.objectContaining({ file_id: 'f1' }),
      'image.filter.task_label',
      'image.filter',
      'photo.png',
    )

    w.unmount()
  })

  it('9. adjust host execute() payload 含完整 11 欄（filter 半沿 meta defaults 中性值）', async () => {
    submitTaskMock.mockResolvedValue('tid')
    const w = mountAdjustHost()
    await flushPromises()

    await (w.vm as any).execute()

    const payload = submitTaskMock.mock.calls[0][1]
    expect(payload).toMatchObject({
      brightness: 1, contrast: 1, saturation: 1, hue: 0, sharpness: 1, warmth: 0,
      grayscale: 0, sepia: 0, invert: 0, blur: 0, vignette: 0,
    })

    w.unmount()
  })
})

describe('FilterParams × ToolParamHost — field-group attrs fallthrough 渲染（順手補，非必須）', () => {
  it('11. adjust host（field-group=adjust attrs 透傳）只渲染 6 個 AppRange（adjust 6 欄）', async () => {
    const w = mountAdjustHost()
    await flushPromises()

    expect(w.findAllComponents(AppRange)).toHaveLength(6)

    w.unmount()
  })
})

describe('FilterParams × ToolParamHost — isMultiSelect prop 透傳', () => {
  it('10. isMultiSelect=true → agentSchema handle.isMultiSelect() 回 true', async () => {
    const w = mountAdjustHost({ isMultiSelect: true })
    await flushPromises()
    const handle = handles.byPanelId.get('image.adjust')

    expect(handle.isMultiSelect()).toBe(true)

    w.unmount()
  })
})
