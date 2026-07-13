/**
 * ToolParamHost + RemoveBgParams 合掛整合測（統一參數元件 spec §6；批 4 Task 4.3）。
 * 取代舊 ImageRemoveBgPanel 的 useAgentPanelHost 手掛，仿 image/__tests__/CompressParams.hostagent.test.ts。
 *
 * 不 stub 參數元件：PARAM_COMPONENTS['image.remove_bg'] 是 defineAsyncComponent 懶載真實
 * RemoveBgParams.vue，mount 後需 flushPromises() 等非同步元件解析完成才有 DOM。
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

// image.remove_bg 無 modelRequirement，preflight 恆真；掛 mock 只為滿足 ToolParamHost
// 無條件呼叫 useModelStore()/useModelGuard() 不炸 no-active-Pinia（同各批 hostagent 慣例）。
vi.mock('@/composables/useModelGuard', () => ({
  useModelGuard: () => ({ guardModelReady: vi.fn(async () => true) }),
}))
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({ models: [] }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
// 預先靜態 import 讓 RemoveBgParams.vue 先進 vitest 模組快取（見 CutParams.hostagent.test.ts
// 同段註記——動態 import 走 Vite transform pipeline，單一 flushPromises() 攔不住）。
import '@/components/params/image/RemoveBgParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'image.remove_bg',
      panelId: 'image.remove_bg',
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

describe('RemoveBgParams × ToolParamHost — agentSchema', () => {
  it('1. fields 名稱集合＝mode，enum 型別，options 沿舊 panel 五選項', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const fields = handle.agentSchema.fields
    expect(fields.map((f: any) => f.name)).toEqual(['mode'])
    expect(fields[0].type).toBe('enum')
    expect(fields[0].options()).toEqual(['auto', 'person', 'product', 'animal', 'anime'])

    w.unmount()
  })

  it('2. execute.requiresConfirm=true（預設）；execute.label="panel.remove_bg.execute"（≠ labelKey，沿舊 agentSchema）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.remove_bg.execute' })

    w.unmount()
  })
})

describe('RemoveBgParams × ToolParamHost — setField（agent 寫入路徑）', () => {
  it('3. setField(mode, "anime") → 回 "anime"，getCurrentValues().mode === "anime"', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('mode', 'anime')).toBe('anime')
    expect(handle.getCurrentValues().mode).toBe('anime')

    w.unmount()
  })

  it('4. setField(mode, "bogus")（非法值）→ 回現值 auto，不寫入', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('mode', 'bogus')).toBe('auto')
    expect(handle.getCurrentValues().mode).toBe('auto')

    w.unmount()
  })
})

describe('RemoveBgParams × ToolParamHost — execute（multiSelect=true）', () => {
  it('5. execute() → submitTask 收到 {file_id,mode:"auto"}，host emit submit', async () => {
    submitTaskMock.mockResolvedValue('tid1')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/image/remove-bg',
      { file_id: 'f1', mode: 'auto' },
      'image.remove_bg.task_label',
      'image.remove_bg',
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
