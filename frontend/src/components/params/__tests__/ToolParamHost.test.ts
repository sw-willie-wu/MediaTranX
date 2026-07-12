/**
 * ToolParamHost 單元測試（統一參數元件 spec §6 / Task 0.5）。
 * stub meta + stub 參數元件；mock useSubmitTask（spy 可查）與 useAgentPanelHost（攔 handle）。
 * 型別/mock 寫法沿用既有 *.agent.test.ts（見 ImageFilterPanel.agent.test.ts）與
 * useAssistantGate.test.ts（vi.hoisted 攔 spy）。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, inject, type PropType } from 'vue'
import type { ToolParamMeta, AgentCompositeField } from '@/components/params/types'
import { PARAM_COMPONENTS, METAS } from '@/components/params/index'

// ─── mocks（vi.mock 工廠只能用 vi.hoisted 建立的變數） ──────────────────────
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

const modelStoreState = vi.hoisted(() => ({ models: [] as Array<{ family: string; variant: string; downloaded: boolean }> }))
vi.mock('@/stores/models', () => ({
  useModelStore: () => modelStoreState,
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'

// ─── stub 參數元件 ───────────────────────────────────────────────────────────
const StubParams = defineComponent({
  name: 'StubParams',
  props: {
    params: { type: Object as PropType<Record<string, unknown>>, required: true },
    context: { type: String, required: true },
    fileInfo: { type: Object as PropType<Record<string, unknown> | null>, default: null },
  },
  emits: ['update:params'],
  setup(_props, { expose }) {
    const notifyLog: Array<{ channel: string; payload: unknown }> = []
    expose({
      notify: (channel: string, payload: unknown) => notifyLog.push({ channel, payload }),
      notifyLog,
    })
    return {}
  },
  render() {
    return h('div', { class: 'stub-params' })
  },
})

// 會在 setup 註冊一個 composite 的 stub 元件（測試案例 7）
const StubParamsWithComposite = defineComponent({
  name: 'StubParamsWithComposite',
  props: {
    params: { type: Object as PropType<Record<string, unknown>>, required: true },
    context: { type: String, required: true },
    fileInfo: { type: Object as PropType<Record<string, unknown> | null>, default: null },
  },
  emits: ['update:params'],
  setup() {
    const register = inject<(c: AgentCompositeField) => () => void>('registerComposite')
    register?.({
      name: 'm',
      covers: ['a'],
      options: () => ['x', 'y'],
      get: () => 'x',
      set: (t: string) => ({ a: t }),
    })
    return {}
  },
  render() {
    return h('div', { class: 'stub-params-composite' })
  },
})

// ─── stub META ───────────────────────────────────────────────────────────────
function makeStubMeta(overrides: Partial<ToolParamMeta> = {}): ToolParamMeta {
  const base: ToolParamMeta = {
    toolKey: 'test.stub',
    apiPath: '/test/stub',
    labelKey: 'test.stub.label',
    taskType: 'test.stub',
    schema: [
      { name: 'a', type: 'number', min: 0, max: 100, default: 5 },
      { name: 'b', type: 'boolean', default: false },
      { name: 'c', type: 'enum', options: ['x', 'y'], default: 'x' },
      { name: 'fmt', type: 'string', default: 'mp4' },
    ],
    defaults() {
      const d: Record<string, unknown> = {}
      for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
      return d
    },
    validate(params) {
      return params.forceInvalid === true ? 'test.stub.invalid' : null
    },
    multiSelect: false,
    downloadFormatField: 'fmt',
    seedOnFileChange(info, _current) {
      if (!info) return null
      return { a: Number(info.seedValue ?? 0) }
    },
  }
  return { ...base, ...overrides }
}

const STUB_TOOL_KEY = 'test.stub'
const STUB_BUILD_SUBMIT_KEY = 'test.stub.buildsubmit'
const STUB_COMPOSITE_KEY = 'test.stub.composite'

METAS[STUB_TOOL_KEY] = makeStubMeta()
PARAM_COMPONENTS[STUB_TOOL_KEY] = StubParams

METAS[STUB_BUILD_SUBMIT_KEY] = makeStubMeta({
  toolKey: STUB_BUILD_SUBMIT_KEY,
  buildSubmit(params) {
    return {
      apiPath: '/test/stub/alt',
      payload: { alt: true, a: params.a },
      taskType: 'test.stub.alt',
      labelKey: 'test.stub.alt.label',
    }
  },
})
PARAM_COMPONENTS[STUB_BUILD_SUBMIT_KEY] = StubParams

METAS[STUB_COMPOSITE_KEY] = makeStubMeta({ toolKey: STUB_COMPOSITE_KEY })
PARAM_COMPONENTS[STUB_COMPOSITE_KEY] = StubParamsWithComposite

// modelRequirement 案（批 1 Task 1.5：preflight × useModelGuard 接線）——remote===true → null，
// 否則回 { slot:'translate', family:'gemma4', size:'4b', quantization:'Q4_K_M' }（固定值，測試無需依賴 params）
const STUB_MODEL_KEY = 'test.stub.model'
METAS[STUB_MODEL_KEY] = makeStubMeta({
  toolKey: STUB_MODEL_KEY,
  modelRequirement(params) {
    if (params.remote === true) return null
    return { slot: 'translate', family: 'gemma4', size: '4b', quantization: 'Q4_K_M' }
  },
})
PARAM_COMPONENTS[STUB_MODEL_KEY] = StubParams

// dict/list 型欄位案（review finding #2：agentSchema.fields 不得含 dict/list 欄位）
const STUB_DICT_KEY = 'test.stub.dict'
METAS[STUB_DICT_KEY] = makeStubMeta({
  toolKey: STUB_DICT_KEY,
  schema: [
    { name: 'a', type: 'number', min: 0, max: 100, default: 5 },
    { name: 'glossary', type: 'dict' },
    { name: 'items', type: 'list' },
  ],
})
PARAM_COMPONENTS[STUB_DICT_KEY] = StubParams

function mountHost(toolKey: string, props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey,
      panelId: toolKey,
      fileId: 'f1',
      currentFileName: 'test.mp4',
      fileInfo: null,
      ...props,
    },
  })
}

beforeEach(() => {
  submitTaskMock.mockReset()
  isProcessingState.value = false
  capturedHandle.current = null
  guardModelReadyMock.mockReset()
  guardModelReadyMock.mockResolvedValue(true)
  modelStoreState.models = []
})

describe('ToolParamHost — params state', () => {
  it('1. defaults seed：mount 後 getParams() 等於 stub meta defaults', () => {
    const w = mountHost(STUB_TOOL_KEY)
    expect((w.vm as any).getParams()).toEqual({ a: 5, b: false, c: 'x', fmt: 'mp4' })
  })

  it('2a. seedOnFileChange：mount 時傳 fileInfo → immediate seed', () => {
    const w = mountHost(STUB_TOOL_KEY, { fileInfo: { seedValue: 42 } })
    expect((w.vm as any).getParams().a).toBe(42)
  })

  it('2b. seedOnFileChange：改 fileInfo prop → 重 seed', async () => {
    const w = mountHost(STUB_TOOL_KEY, { fileInfo: { seedValue: 1 } })
    expect((w.vm as any).getParams().a).toBe(1)
    await w.setProps({ fileInfo: { seedValue: 99 } })
    expect((w.vm as any).getParams().a).toBe(99)
  })
})

describe('ToolParamHost — setField coerce', () => {
  it('3a. number: "24" → 24', () => {
    const w = mountHost(STUB_TOOL_KEY)
    expect((w.vm as any).setField('a', '24')).toBe(24)
    expect((w.vm as any).getParams().a).toBe(24)
  })

  it('3b. boolean: "x" → true', () => {
    const w = mountHost(STUB_TOOL_KEY)
    expect((w.vm as any).setField('b', 'x')).toBe(true)
    expect((w.vm as any).getParams().b).toBe(true)
  })

  it('3c. enum 非法值 → 回現值、params 不變', () => {
    const w = mountHost(STUB_TOOL_KEY)
    const result = (w.vm as any).setField('c', 'nope')
    expect(result).toBe('x') // 現值 default
    expect((w.vm as any).getParams().c).toBe('x')
  })

  it('3d. 未知欄位 throw', () => {
    const w = mountHost(STUB_TOOL_KEY)
    expect(() => (w.vm as any).setField('ghost', 1)).toThrow(/unknown field/i)
  })

  it('3e. number 非有限數 → 回現值不寫', () => {
    const w = mountHost(STUB_TOOL_KEY)
    const result = (w.vm as any).setField('a', 'not-a-number')
    expect(result).toBe(5)
    expect((w.vm as any).getParams().a).toBe(5)
  })
})

describe('ToolParamHost — setParams / resetToDefaults', () => {
  it('4a. setParams 整顆替換（未列欄位被清除）', () => {
    const w = mountHost(STUB_TOOL_KEY)
    ;(w.vm as any).setParams({ a: 1 })
    expect((w.vm as any).getParams()).toEqual({ a: 1 })
  })

  it('4b. resetToDefaults 回 defaults', () => {
    const w = mountHost(STUB_TOOL_KEY)
    ;(w.vm as any).setParams({ a: 1 })
    ;(w.vm as any).resetToDefaults()
    expect((w.vm as any).getParams()).toEqual({ a: 5, b: false, c: 'x', fmt: 'mp4' })
  })
})

describe('ToolParamHost — getSubmitSpec', () => {
  it('5a. 無 buildSubmit → 直傳形狀（payload 無 file_id）', () => {
    const w = mountHost(STUB_TOOL_KEY)
    const spec = (w.vm as any).getSubmitSpec()
    expect(spec).toEqual({
      apiPath: '/test/stub',
      payload: { a: 5, b: false, c: 'x', fmt: 'mp4' },
      taskType: 'test.stub',
      labelKey: 'test.stub.label',
    })
    expect(spec.payload.file_id).toBeUndefined()
  })

  it('5b. 有 buildSubmit → 走 buildSubmit 且 payload 無 file_id', () => {
    const w = mountHost(STUB_BUILD_SUBMIT_KEY)
    const spec = (w.vm as any).getSubmitSpec()
    expect(spec).toEqual({
      apiPath: '/test/stub/alt',
      payload: { alt: true, a: 5 },
      taskType: 'test.stub.alt',
      labelKey: 'test.stub.alt.label',
    })
    expect(spec.payload.file_id).toBeUndefined()
  })
})

describe('ToolParamHost — execute', () => {
  it('6a. validate 失敗 → submitTask 不被呼叫', async () => {
    const w = mountHost(STUB_TOOL_KEY)
    ;(w.vm as any).setParams({ a: 5, b: false, c: 'x', fmt: 'mp4', forceInvalid: true })
    await (w.vm as any).execute()
    expect(submitTaskMock).not.toHaveBeenCalled()
  })

  it('6b. 成功 → submitTask 收到 {file_id, ...payload} 且 emit submit', async () => {
    submitTaskMock.mockResolvedValue('task-123')
    const w = mountHost(STUB_TOOL_KEY)
    const result = await (w.vm as any).execute()
    expect(submitTaskMock).toHaveBeenCalledWith(
      '/test/stub',
      { file_id: 'f1', a: 5, b: false, c: 'x', fmt: 'mp4' },
      'test.stub.label',
      'test.stub',
      'test.mp4',
    )
    expect(result).toEqual({ task_id: 'task-123' })
    expect(w.emitted('submit')).toEqual([['task-123']])
  })
})

describe('ToolParamHost — composite 兩層合成', () => {
  it('7. agentSchema.fields 無 a、有 m；setField(m,y) 改 a；getCurrentValues 含 m 不含 a', () => {
    const w = mountHost(STUB_COMPOSITE_KEY)
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const names = handle.agentSchema.fields.map((f: any) => f.name)
    expect(names).not.toContain('a')
    expect(names).toContain('m')

    const mField = handle.agentSchema.fields.find((f: any) => f.name === 'm')
    expect(mField.type).toBe('enum')
    expect(mField.options()).toEqual(['x', 'y'])

    handle.setField('m', 'y')
    expect((w.vm as any).getParams().a).toBe('y')

    const values = handle.getCurrentValues()
    expect(values.m).toBe('x')
    expect(values).not.toHaveProperty('a')
  })
})

describe('ToolParamHost — agentSchema dict/list 排除（review finding #2）', () => {
  it('8. dict/list 型欄位不進 agentSchema.fields；scalar 欄位不受影響', () => {
    const w = mountHost(STUB_DICT_KEY)
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const names = handle.agentSchema.fields.map((f: any) => f.name)
    expect(names).not.toContain('glossary')
    expect(names).not.toContain('items')
    expect(names).toContain('a')

    // dict/list 欄位仍留在 params 全集裡（getCurrentValues／execute payload 不受影響）
    ;(w.vm as any).setParams({ a: 1, glossary: { foo: 'bar' }, items: [1, 2] })
    const values = handle.getCurrentValues()
    expect(values.glossary).toEqual({ foo: 'bar' })
    expect(values.items).toEqual([1, 2])
  })
})

describe('ToolParamHost — preflight × useModelGuard（批 1 Task 1.5 接線）', () => {
  it('a. meta 無 modelRequirement → preflight 恆 true，不呼叫 guardModelReady', async () => {
    const w = mountHost(STUB_TOOL_KEY)
    await expect((w.vm as any).preflight()).resolves.toBe(true)
    expect(guardModelReadyMock).not.toHaveBeenCalled()
  })

  it('b. modelRequirement 非 null，modelStore 有對應 family/variant 且已下載 → guardModelReady(true, 對照分類)', async () => {
    modelStoreState.models = [{ family: 'gemma4', variant: '4b:Q4_K_M', downloaded: true }]
    const w = mountHost(STUB_MODEL_KEY)
    const ready = await (w.vm as any).preflight()
    expect(guardModelReadyMock).toHaveBeenCalledWith(true, 'llm')
    expect(ready).toBe(true)
  })

  it('c. modelRequirement 非 null，modelStore 無對應項（未下載）→ guardModelReady(false, ...)，preflight 回傳 guard 結果', async () => {
    modelStoreState.models = []
    guardModelReadyMock.mockResolvedValueOnce(false)
    const w = mountHost(STUB_MODEL_KEY)
    const ready = await (w.vm as any).preflight()
    expect(guardModelReadyMock).toHaveBeenCalledWith(false, 'llm')
    expect(ready).toBe(false)
  })

  it('d. execute()：preflight 回 false → submitTask 不被呼叫', async () => {
    guardModelReadyMock.mockResolvedValueOnce(false)
    const w = mountHost(STUB_MODEL_KEY)
    const result = await (w.vm as any).execute()
    expect(submitTaskMock).not.toHaveBeenCalled()
    expect(result).toEqual({})
  })

  it('e. execute()：validate 失敗優先於 preflight（validate 先擋，guardModelReady 不被呼叫）', async () => {
    const w = mountHost(STUB_MODEL_KEY)
    ;(w.vm as any).setParams({ a: 5, b: false, c: 'x', fmt: 'mp4', forceInvalid: true })
    await (w.vm as any).execute()
    expect(guardModelReadyMock).not.toHaveBeenCalled()
    expect(submitTaskMock).not.toHaveBeenCalled()
  })
})

describe('ToolParamHost — isDisabled', () => {
  it('8a. 無 fileId → true', () => {
    const w = mountHost(STUB_TOOL_KEY, { fileId: null })
    expect((w.vm as any).isDisabled).toBe(true)
  })

  it('8b. 有 fileId＋validate null → false', () => {
    const w = mountHost(STUB_TOOL_KEY, { fileId: 'f1' })
    expect((w.vm as any).isDisabled).toBe(false)
  })

  it('8c. validate 非 null → true', () => {
    const w = mountHost(STUB_TOOL_KEY, { fileId: 'f1' })
    ;(w.vm as any).setParams({ a: 5, b: false, c: 'x', fmt: 'mp4', forceInvalid: true })
    expect((w.vm as any).isDisabled).toBe(true)
  })
})

describe('ToolParamHost — outputFormat', () => {
  it('9. downloadFormatField=fmt，params.fmt=mp4 → "mp4"', () => {
    const w = mountHost(STUB_TOOL_KEY)
    expect((w.vm as any).outputFormat).toBe('mp4')
  })
})

describe('ToolParamHost — notify（機制驗證，非 brief 列舉案例）', () => {
  it('轉呼參數元件 defineExpose 的 notify()', () => {
    const w = mountHost(STUB_TOOL_KEY)
    ;(w.vm as any).notify('trim', { start: 1, end: 2 })
    const stubVm = w.findComponent(StubParams).vm as any
    expect(stubVm.notifyLog).toEqual([{ channel: 'trim', payload: { start: 1, end: 2 } }])
  })
})
