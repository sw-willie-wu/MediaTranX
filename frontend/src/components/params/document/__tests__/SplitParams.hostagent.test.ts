/**
 * ToolParamHost + SplitParams 合掛整合測（統一參數元件 spec §6；批 4 Task 4.5 Part A）。
 * 取代舊 DocumentSplitPanel 的 useAgentPanelHost 手掛＋DocumentSplitPanel.agent.test.ts，
 * 仿 image/__tests__/RemoveBgParams.hostagent.test.ts。
 *
 * 不 stub 參數元件：PARAM_COMPONENTS['document.split'] 是 defineAsyncComponent 懶載真實
 * SplitParams.vue，mount 後需 flushPromises() 等非同步元件解析完成才有 DOM。
 *
 * seedOnFileChange 的合成 fileInfo 觸發源（見 split.meta.ts 檔頭註解）：本測試以
 * `{ fileId }` 形狀模擬 DocumentView.vue 掛載點的實際傳法，驗證換檔（fileInfo 物件參考變化）
 * 會清空 pages。
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

// document.split 無 modelRequirement，preflight 恆真；掛 mock 只為滿足 ToolParamHost
// 無條件呼叫 useModelStore()/useModelGuard() 不炸 no-active-Pinia（同各批 hostagent 慣例）。
vi.mock('@/composables/useModelGuard', () => ({
  useModelGuard: () => ({ guardModelReady: vi.fn(async () => true) }),
}))
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({ models: [] }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
// 預先靜態 import 讓 SplitParams.vue 先進 vitest 模組快取（見 CutParams.hostagent.test.ts
// 檔頭記載的動態 import race 問題與解法）。
import '@/components/params/document/SplitParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'document.split',
      panelId: 'document.split',
      fileId: 'f1',
      currentFileName: 'report.pdf',
      fileInfo: { fileId: 'f1' },
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

describe('document.split × ToolParamHost — agentSchema', () => {
  it('1. fields 名稱集合＝pages，string 型別', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const fields = handle.agentSchema.fields
    expect(fields.map((f: any) => f.name)).toEqual(['pages'])
    expect(fields[0].type).toBe('string')

    w.unmount()
  })

  it('2. execute.requiresConfirm=false；execute.label="panel.doc_split.execute"', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: false, label: 'panel.doc_split.execute' })

    w.unmount()
  })
})

describe('document.split × ToolParamHost — setField（agent 寫入路徑）', () => {
  it('3. setField(pages, "1-3,5") → 回 "1-3,5"，getCurrentValues().pages === "1-3,5"', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('pages', '1-3,5')).toBe('1-3,5')
    expect(handle.getCurrentValues().pages).toBe('1-3,5')

    w.unmount()
  })
})

describe('document.split × ToolParamHost — execute（multiSelect=true）', () => {
  it('4. execute() → submitTask 收到 {file_id,pages}，host emit submit', async () => {
    submitTaskMock.mockResolvedValue('tid1')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    handle.setField('pages', '1-3')

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/document/split',
      { file_id: 'f1', pages: '1-3' },
      'document.split.task_label',
      'document.split',
      'report.pdf',
    )
    expect(result).toEqual({ task_id: 'tid1' })
    expect(w.emitted('submit')).toEqual([['tid1']])

    w.unmount()
  })

  it('5. isMultiSelect prop=true → agentSchema handle.isMultiSelect() 回 true', async () => {
    const w = mountHost({ isMultiSelect: true })
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.isMultiSelect()).toBe(true)

    w.unmount()
  })
})

describe('document.split × ToolParamHost — seedOnFileChange（換檔清空 pages）', () => {
  it('6. 換檔（fileInfo 物件參考變化）→ pages 被清空', async () => {
    const w = mountHost({ fileInfo: { fileId: 'f1' } })
    await flushPromises()
    const handle = capturedHandle.current
    handle.setField('pages', '1-3')
    expect(handle.getCurrentValues().pages).toBe('1-3')

    await w.setProps({ fileInfo: { fileId: 'f2' } })
    await flushPromises()

    expect(handle.getCurrentValues().pages).toBe('')

    w.unmount()
  })
})
