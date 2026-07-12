/**
 * ToolParamHost + PdfConvertParams 合掛整合測（統一參數元件 spec §6；批 4 Task 4.5 Part B）。
 * 取代舊 DocumentPdfConvertPanel 的 useAgentPanelHost 手掛＋
 * DocumentPdfConvertPanel.agent.test.ts，仿 image/__tests__/RemoveBgParams.hostagent.test.ts。
 *
 * 不 stub 參數元件：PARAM_COMPONENTS['document.pdf_convert'] 是 defineAsyncComponent 懶載
 * 真實 PdfConvertParams.vue，mount 後需 flushPromises() 等非同步元件解析完成才有 DOM。
 *
 * current-file-ext fallthrough attrs（DocumentView.vue 實際掛法）另見本檔末段——仿
 * OcrParams.hostagent.test.ts 的 persist-key/i18n-prefix 驗證手法。
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

// document.pdf_convert 無 modelRequirement，preflight 恆真；掛 mock 只為滿足 ToolParamHost
// 無條件呼叫 useModelStore()/useModelGuard() 不炸 no-active-Pinia（同各批 hostagent 慣例）。
vi.mock('@/composables/useModelGuard', () => ({
  useModelGuard: () => ({ guardModelReady: vi.fn(async () => true) }),
}))
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({ models: [] }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
import AppSelect from '@/components/common/AppSelect.vue'
// 預先靜態 import 讓 PdfConvertParams.vue 先進 vitest 模組快取（見 CutParams.hostagent.test.ts
// 檔頭記載的動態 import race 問題與解法）。
import '@/components/params/document/PdfConvertParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'document.pdf_convert',
      panelId: 'document.pdf_convert',
      fileId: 'f1',
      currentFileName: 'report.pdf',
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

describe('document.pdf_convert × ToolParamHost — agentSchema', () => {
  it('1. fields 名稱集合＝output_format，enum 型別，options 為後端全集 txt/md/images（見 meta 檔頭「agent 面擴大」決策）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const fields = handle.agentSchema.fields
    expect(fields.map((f: any) => f.name)).toEqual(['output_format'])
    expect(fields[0].type).toBe('enum')
    expect(fields[0].options()).toEqual(['txt', 'md', 'images'])

    w.unmount()
  })

  it('2. execute.requiresConfirm=false；execute.label="panel.doc_pdf_convert.execute"', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.agentSchema.execute).toEqual({ requiresConfirm: false, label: 'panel.doc_pdf_convert.execute' })

    w.unmount()
  })
})

describe('document.pdf_convert × ToolParamHost — setField（agent 寫入路徑）', () => {
  it('3. setField(output_format, "md") → 回 "md"，getCurrentValues().output_format === "md"', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('output_format', 'md')).toBe('md')
    expect(handle.getCurrentValues().output_format).toBe('md')

    w.unmount()
  })

  it('4. setField(output_format, "bogus")（非法值）→ 回現值 txt，不寫入', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('output_format', 'bogus')).toBe('txt')
    expect(handle.getCurrentValues().output_format).toBe('txt')

    w.unmount()
  })
})

describe('document.pdf_convert × ToolParamHost — execute（multiSelect=true）', () => {
  it('5. execute() → submitTask 收到 {file_id,output_format:"txt"}，host emit submit', async () => {
    submitTaskMock.mockResolvedValue('tid1')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/document/pdf-convert',
      { file_id: 'f1', output_format: 'txt' },
      'document.pdf_convert.task_label',
      'document.pdf_convert',
      'report.pdf',
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

describe('document.pdf_convert × ToolParamHost — current-file-ext fallthrough attrs（DocumentView.vue 實際掛法）', () => {
  it('7. ToolParamHost 上的 kebab-case current-file-ext 透過 $attrs fallthrough 轉發到 PdfConvertParams（非 pdf → images 選項隱藏）', async () => {
    const w = mountHost({ 'current-file-ext': 'docx' })
    await flushPromises()

    const fields = capturedHandle.current.agentSchema.fields
    // agent 面固定看到後端全集（見 test 1）——這裡改驗 UI 層（AppSelect 的 options prop）確有收窄。
    expect(fields[0].options()).toEqual(['txt', 'md', 'images'])
    const select = w.findComponent(AppSelect)
    const values = (select.props('options') as Array<{ value: string }>).map((o) => o.value)
    expect(values).not.toContain('images')

    w.unmount()
  })

  it('8. current-file-ext="pdf" 轉發後 images 選項存在', async () => {
    const w = mountHost({ 'current-file-ext': 'pdf' })
    await flushPromises()

    const select = w.findComponent(AppSelect)
    const values = (select.props('options') as Array<{ value: string }>).map((o) => o.value)
    expect(values).toContain('images')

    w.unmount()
  })
})
