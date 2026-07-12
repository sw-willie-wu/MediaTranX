/**
 * pipeline store — startRun 前逐節點模型驗證（Task 1.6）。
 * PipelineRunner 整套 mock 掉：本測試只關心「起跑前的 model_missing 驗證/放行」邊界，
 * 不驗證引擎本體執行（那是 pipeline/__tests__/runner.test.ts 的職責）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const runnerCtor = vi.fn()
const runnerStart = vi.fn(async () => {})
const runnerSnapshot = vi.fn(() => ({ status: 'completed', executions: [], truncatedNodes: [] }))

vi.mock('@/pipeline/runner', async () => {
  const actual = await vi.importActual<typeof import('@/pipeline/runner')>('@/pipeline/runner')
  class FakePipelineRunner {
    constructor(...args: unknown[]) {
      runnerCtor(...args)
    }
    start = runnerStart
    snapshot = runnerSnapshot
    cancel = vi.fn(async () => {})
  }
  return { ...actual, PipelineRunner: FakePipelineRunner }
})

import { usePipelineStore } from '@/stores/pipeline'
import { useModelStore } from '@/stores/models'
import type { Recipe } from '@/pipeline/types'

function translateRecipe(params: Record<string, unknown> = {}): Recipe {
  return {
    version: 1,
    name: 'r',
    nodes: [
      { id: 'input-1', kind: 'input', params: {}, position: { x: 0, y: 0 } },
      {
        id: 'n2',
        kind: 'tool',
        toolKey: 'document.translate',
        params: {
          source_language: 'en',
          target_language: 'zh-TW',
          model_family: 'gemma4',
          model_size: '4b',
          quantization: 'Q4_K_M',
          remote: false,
          ...params,
        },
        position: { x: 100, y: 0 },
      },
    ],
    edges: [{ from: 'input-1', to: 'n2' }],
  }
}

function cutRecipe(): Recipe {
  return {
    version: 1,
    name: 'r',
    nodes: [
      { id: 'input-1', kind: 'input', params: {}, position: { x: 0, y: 0 } },
      { id: 'n2', kind: 'tool', toolKey: 'video.cut', params: { start: 0, end: 1 }, position: { x: 100, y: 0 } },
    ],
    edges: [{ from: 'input-1', to: 'n2' }],
  }
}

describe('pipeline store — startRun 前模型驗證', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    runnerCtor.mockClear()
    runnerStart.mockClear()
    runnerSnapshot.mockClear()
  })

  function seedModels(models: Array<{ family: string; variant: string; downloaded: boolean }>) {
    const modelStore = useModelStore()
    modelStore.models = models as never
    modelStore.loaded = true // ensureLoaded 因此不會真的打 API
  }

  it('1. local 模型未安裝 → startRun 不啟動、issues 含 model_missing（nodeId 對）', async () => {
    seedModels([{ family: 'gemma4', variant: '4b:Q4_K_M', downloaded: false }])
    const store = usePipelineStore()
    store.recipe = translateRecipe()
    store.inputFiles = [{ fileId: 'f1', filename: 'a.pdf' }]

    await store.startRun()

    expect(runnerCtor).not.toHaveBeenCalled()
    expect(store.running).toBe(false)
    const missing = store.issues.filter(i => i.code === 'model_missing')
    expect(missing).toHaveLength(1)
    expect(missing[0].nodeId).toBe('n2')
    expect(missing[0].severity).toBe('error')
    expect(store.errors.some(i => i.code === 'model_missing')).toBe(true)
  })

  it('2. remote:true → 照常啟動（runner 被呼叫），不做模型檢查', async () => {
    seedModels([]) // 空清單也無妨——remote 分支不查
    const store = usePipelineStore()
    store.recipe = translateRecipe({ remote: true })
    store.inputFiles = [{ fileId: 'f1', filename: 'a.pdf' }]

    await store.startRun()

    expect(runnerCtor).toHaveBeenCalledTimes(1)
    expect(runnerStart).toHaveBeenCalledTimes(1)
    expect(store.issues.some(i => i.code === 'model_missing')).toBe(false)
  })

  it('3. 模型已安裝 → 照常啟動', async () => {
    seedModels([{ family: 'gemma4', variant: '4b:Q4_K_M', downloaded: true }])
    const store = usePipelineStore()
    store.recipe = translateRecipe()
    store.inputFiles = [{ fileId: 'f1', filename: 'a.pdf' }]

    await store.startRun()

    expect(runnerCtor).toHaveBeenCalledTimes(1)
    expect(runnerStart).toHaveBeenCalledTimes(1)
    expect(store.issues.some(i => i.code === 'model_missing')).toBe(false)
  })

  it('4. 無 modelRequirement 的節點（video.cut）→ 不受影響，照常啟動', async () => {
    seedModels([])
    const store = usePipelineStore()
    store.recipe = cutRecipe()
    store.inputFiles = [{ fileId: 'f1', filename: 'a.mp4' }]

    await store.startRun()

    expect(runnerCtor).toHaveBeenCalledTimes(1)
    expect(runnerStart).toHaveBeenCalledTimes(1)
    expect(store.issues.some(i => i.code === 'model_missing')).toBe(false)
  })

  it('5. model_missing 後補裝再 startRun → 過（issues 清除）', async () => {
    const modelStore = useModelStore()
    modelStore.models = [{ family: 'gemma4', variant: '4b:Q4_K_M', downloaded: false }] as never
    modelStore.loaded = true
    const store = usePipelineStore()
    store.recipe = translateRecipe()
    store.inputFiles = [{ fileId: 'f1', filename: 'a.pdf' }]

    await store.startRun()
    expect(store.issues.some(i => i.code === 'model_missing')).toBe(true)
    expect(runnerCtor).not.toHaveBeenCalled()

    // 補裝
    modelStore.models = [{ family: 'gemma4', variant: '4b:Q4_K_M', downloaded: true }] as never

    await store.startRun()
    expect(store.issues.some(i => i.code === 'model_missing')).toBe(false)
    expect(runnerCtor).toHaveBeenCalledTimes(1)
  })

  it('canRun 不因 model_missing 被永久鎖死（結構合法時恆 true，供重按執行）', async () => {
    seedModels([{ family: 'gemma4', variant: '4b:Q4_K_M', downloaded: false }])
    const store = usePipelineStore()
    store.recipe = translateRecipe()
    store.inputFiles = [{ fileId: 'f1', filename: 'a.pdf' }]

    expect(store.canRun).toBe(true)
    await store.startRun()
    expect(store.issues.some(i => i.code === 'model_missing')).toBe(true)
    // 執行鈕仍可再按（canRun 不看 modelIssues）
    expect(store.canRun).toBe(true)
  })
})
