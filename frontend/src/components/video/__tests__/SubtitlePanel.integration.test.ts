/**
 * SubtitlePanel 殼整合測（統一參數元件案批 2 Task 2.5——例外殼）。
 * 覆蓋：
 *  - agent setField 經 params 讀寫（getCurrentValues 反映 setField 寫入）
 *  - submitGenerate() body 與舊 body 等價（完整形狀斷言，見 subtitle.meta.test.ts buildSubmit
 *    測試涵蓋的 gate 邏輯；本檔驗證殼層 apiFetch/addTask/toast 接線正確）
 *  - preflight guard（modelRequirements × guardModelReady）依序檢查、未就緒即中止
 *
 * SubtitleParams.vue 本身另有專測（SubtitleParams.test.ts），本檔 mock 掉它，只測殼的職責。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { h } from 'vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

const addTaskMock = vi.hoisted(() => vi.fn())
vi.mock('@/stores/tasks', () => ({
  useTaskStore: () => ({ addTask: addTaskMock }),
}))

vi.mock('@/stores/files', () => ({
  useFilesStore: () => ({ currentFile: { originalName: 'video.mp4' } }),
}))

const toastShowMock = vi.hoisted(() => vi.fn())
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ show: toastShowMock }),
}))

const apiFetchMock = vi.hoisted(() => vi.fn())
vi.mock('@/composables/useApi', () => ({
  apiFetch: apiFetchMock,
}))

const modelStoreState = vi.hoisted(() => ({
  models: [] as Array<{ family: string; variant: string; downloaded: boolean; category?: string; subcategory?: string }>,
}))
const modelEnsureLoadedMock = vi.hoisted(() => vi.fn())
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    models: modelStoreState.models,
    byCategory: (cat: string) => modelStoreState.models.filter((m) => m.category === cat),
    forPanel: (x: unknown[]) => x,
    ensureLoaded: modelEnsureLoadedMock,
  }),
}))

const guardModelReadyMock = vi.hoisted(() => vi.fn(async () => true))
vi.mock('@/composables/useModelGuard', () => ({
  useModelGuard: () => ({ guardModelReady: guardModelReadyMock }),
}))

const capturedHandle = vi.hoisted(() => ({ current: null as any }))
vi.mock('@/composables/useAgentPanelHost', () => ({
  useAgentPanelHost: (_panelId: string, handle: any) => {
    capturedHandle.current = handle
  },
}))

// SubtitleParams 本身另有專測，本檔只需一個可控制 emit 的 stub。
// 注意：vi.mock 工廠會被 hoist 到檔案最上方，不能參照下方才初始化的 top-level const
// （defineComponent(...) 的結果）——直接在工廠內用物件字面量定義，import 進來的 h/PropType
// 屬於「已 hoist 的 import binding」不受此限制。
vi.mock('@/components/params/video/SubtitleParams.vue', () => ({
  default: {
    name: 'SubtitleParamsStub',
    props: {
      params: { type: Object, required: true },
      context: { type: String, required: true },
      fileInfo: { type: Object, default: null },
      languageOptions: { type: Array, default: undefined },
    },
    emits: ['update:params'],
    render() {
      return h('div', { class: 'stub-subtitle-params' })
    },
  },
}))

import SubtitlePanel from '../SubtitlePanel.vue'
import SubtitleParamsStub from '@/components/params/video/SubtitleParams.vue'

function mountPanel(fileId: string | null = 'file-1') {
  return mount(SubtitlePanel, {
    props: { fileId, mediaInfo: null },
    global: { mocks: { $t: (k: string) => k } },
  })
}

function setParams(w: ReturnType<typeof mountPanel>, patch: Record<string, unknown>) {
  const stub = w.findComponent(SubtitleParamsStub)
  const current = stub.props('params') as Record<string, unknown>
  stub.vm.$emit('update:params', { ...current, ...patch })
}

/** apiFetch 被殼呼叫兩種用途：onMounted 的 loadLanguages()（GET /audio/transcribe/languages，
 * 回陣列）與 submitGenerate()（POST /video/subtitle/generate，回 {task_id}）——依 path 分流回應,
 * 避免 loadLanguages 用 generate 的回應形狀爆炸（rawLanguages.value.map 對非陣列噴錯）。 */
function generateCall() {
  return apiFetchMock.mock.calls.find(([path]) => path === '/video/subtitle/generate')
}

beforeEach(() => {
  modelStoreState.models = []
  addTaskMock.mockClear()
  toastShowMock.mockClear()
  apiFetchMock.mockReset()
  apiFetchMock.mockImplementation(async (path: string) => {
    if (path === '/audio/transcribe/languages') return { ok: true, json: async () => [] }
    return { ok: true, json: async () => ({ task_id: 'task-1' }) }
  })
  modelEnsureLoadedMock.mockClear()
  guardModelReadyMock.mockReset()
  guardModelReadyMock.mockResolvedValue(true)
})

describe('SubtitlePanel — agent setField 經 params 讀寫', () => {
  it('setField 四欄 → getCurrentValues 反映新值', () => {
    const w = mountPanel()
    const handle = capturedHandle.current
    expect(handle.setField('language', 'en')).toBe('en')
    expect(handle.setField('whisper_model', 'large-v3')).toBe('large-v3')
    expect(handle.setField('vocal_separation', true)).toBe(true)
    expect(handle.setField('output_format', 'vtt')).toBe('vtt')
    expect(handle.getCurrentValues()).toEqual({
      language: 'en',
      whisper_model: 'large-v3',
      vocal_separation: true,
      output_format: 'vtt',
    })
    w.unmount()
  })

  it('未知欄位 → throw', () => {
    mountPanel()
    const handle = capturedHandle.current
    expect(() => handle.setField('unknown', 'x')).toThrow()
  })

  it('isMultiSelect 恆 false（m16）', () => {
    mountPanel()
    expect(capturedHandle.current.isMultiSelect()).toBe(false)
  })

  it('agentSchema.execute.label = panel.subtitle.execute（沿舊字面值）', () => {
    mountPanel()
    expect(capturedHandle.current.agentSchema.execute).toEqual({ requiresConfirm: true, label: 'panel.subtitle.execute' })
  })
})

describe('SubtitlePanel — submitGenerate() body 與舊等價（無翻譯）', () => {
  it('預設 params → body 不含 translate_*，taskType/label 為未翻譯版本', async () => {
    const w = mountPanel('file-1')
    await (w.vm as any).submitGenerate()

    const call = generateCall()
    expect(call).toBeDefined()
    const [path, init] = call!
    expect(path).toBe('/video/subtitle/generate')
    const body = JSON.parse((init as RequestInit).body as string)
    expect(body).toEqual({
      file_id: 'file-1',
      model_size: 'medium',
      output_format: 'srt',
      vocal_separation: false,
      word_timestamps: false,
      align: false,
      condition_on_previous_text: true,
      min_silence_duration_ms: 200,
      vad_threshold: 0.3,
    })

    expect(addTaskMock).toHaveBeenCalledTimes(1)
    const addTaskArg = addTaskMock.mock.calls[0][0]
    expect(addTaskArg.taskId).toBe('task-1')
    expect(addTaskArg.taskType).toBe('subtitle/generate')
    expect(addTaskArg.label).toBe('video.subtitle.task_label')
    expect(addTaskArg.fileName).toBe('video.mp4')

    expect(toastShowMock).toHaveBeenCalledTimes(1)
    w.unmount()
  })
})

describe('SubtitlePanel — submitGenerate() body 與舊等價（翻譯已啟用）', () => {
  it('target_language 有值 → body 含 translate_* 七欄之必要子集 + keep_names/translate_style，label 為 with_translate', async () => {
    const w = mountPanel('file-1')
    setParams(w, {
      source_language: 'en',
      target_language: 'zh-TW',
      translate_model_family: 'gemma4',
      translate_model_size: '4b',
      keep_names: false,
      translate_style: 'formal',
      glossary: { A: 'B' },
    })
    await (w.vm as any).submitGenerate()

    const [, init] = generateCall()!
    const body = JSON.parse((init as RequestInit).body as string)
    expect(body.source_language).toBe('en')
    expect(body.target_language).toBe('zh-TW')
    expect(body.translate_model_family).toBe('gemma4')
    expect(body.translate_model_size).toBe('4b')
    expect(body.keep_names).toBe(false)
    expect(body.translate_style).toBe('formal')
    expect(body.glossary).toEqual({ A: 'B' })
    expect(body.translate_remote).toBeUndefined()

    const addTaskArg = addTaskMock.mock.calls[0][0]
    expect(addTaskArg.label).toBe('video.subtitle.task_label_with_translate')
    w.unmount()
  })
})

describe('SubtitlePanel — preflight guard（modelRequirements 依序）', () => {
  it('whisper 未就緒 → guardModelReady(false,"audio")，中止提交（apiFetch 不呼叫）', async () => {
    guardModelReadyMock.mockResolvedValueOnce(false)
    const w = mountPanel('file-1')
    await (w.vm as any).submitGenerate()
    expect(guardModelReadyMock).toHaveBeenCalledWith(false, 'audio')
    expect(generateCall()).toBeUndefined()
    w.unmount()
  })

  it('whisper 已裝、vocal_separation 開啟且 demucs 未裝 → 第二道 guard 攔截', async () => {
    modelStoreState.models = [
      { family: 'whisper', variant: 'medium', downloaded: true, category: 'stt' },
    ]
    guardModelReadyMock.mockResolvedValueOnce(true).mockResolvedValueOnce(false)
    const w = mountPanel('file-1')
    setParams(w, { vocal_separation: true })
    await (w.vm as any).submitGenerate()
    expect(guardModelReadyMock).toHaveBeenCalledTimes(2)
    expect(guardModelReadyMock).toHaveBeenNthCalledWith(2, false, 'audio')
    expect(generateCall()).toBeUndefined()
    w.unmount()
  })

  it('翻譯已啟用且非 remote → 第四道 guard 傳 "llm" 分類', async () => {
    modelStoreState.models = [
      { family: 'whisper', variant: 'medium', downloaded: true, category: 'stt' },
      { family: 'gemma4', variant: '4b:Q4_K_M', downloaded: true },
    ]
    const w = mountPanel('file-1')
    setParams(w, { target_language: 'zh-TW', translate_model_family: 'gemma4', translate_model_size: '4b' })
    await (w.vm as any).submitGenerate()
    expect(guardModelReadyMock).toHaveBeenCalledWith(true, 'llm')
    w.unmount()
  })

  it('翻譯 remote=true → 不追加 translate guard（只呼叫 whisper 一次）', async () => {
    modelStoreState.models = [
      { family: 'whisper', variant: 'medium', downloaded: true, category: 'stt' },
    ]
    const w = mountPanel('file-1')
    setParams(w, { target_language: 'zh-TW', translate_remote: true })
    await (w.vm as any).submitGenerate()
    expect(guardModelReadyMock).toHaveBeenCalledTimes(1)
    w.unmount()
  })
})

describe('SubtitlePanel — isDisabled / defineExpose 契約', () => {
  it('無 fileId → isDisabled true', () => {
    const w = mountPanel(null)
    expect((w.vm as any).isDisabled).toBe(true)
    w.unmount()
  })

  it('有 fileId 且非 loading → isDisabled false', () => {
    const w = mountPanel('file-1')
    expect((w.vm as any).isDisabled).toBe(false)
    w.unmount()
  })

  it('defineExpose 契約不變：submitGenerate/isLoading/isDisabled', () => {
    const w = mountPanel('file-1')
    expect(typeof (w.vm as any).submitGenerate).toBe('function')
    expect((w.vm as any).isLoading).toBeDefined()
    expect((w.vm as any).isDisabled).toBeDefined()
    w.unmount()
  })
})
