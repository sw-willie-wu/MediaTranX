/**
 * pipeline store 多文件化（分頁）核心——代理層、runningDocId 全域鎖、
 * per-doc modelIssues、startRun 競態（spec §5.1/§5.2、§8）。
 * PipelineRunner 整套 mock（同 pipeline.modelGuard.test.ts 手法）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const runnerCtor = vi.fn()
let runnerStartImpl: () => Promise<void> = async () => {}
const runnerStart = vi.fn(() => runnerStartImpl())
const runnerSnapshot = vi.fn(() => ({ status: 'completed', executions: [], truncatedNodes: [] }))

vi.mock('@/pipeline/runner', async () => {
  const actual = await vi.importActual<typeof import('@/pipeline/runner')>('@/pipeline/runner')
  class FakePipelineRunner {
    constructor(...args: unknown[]) { runnerCtor(...args) }
    start = runnerStart
    snapshot = runnerSnapshot
    cancel = vi.fn(async () => {})
  }
  return { ...actual, PipelineRunner: FakePipelineRunner }
})

import { usePipelineStore } from '@/stores/pipeline'
import { useModelStore } from '@/stores/models'
import type { Recipe } from '@/pipeline/types'

function translateRecipe(): Recipe {
  return {
    version: 1,
    name: 'r',
    nodes: [
      { id: 'input-1', kind: 'input', params: {}, position: { x: 0, y: 0 } },
      {
        id: 'n2', kind: 'tool', toolKey: 'document.translate',
        params: {
          source_language: 'en', target_language: 'zh-TW',
          model_family: 'gemma4', model_size: '4b', quantization: 'Q4_K_M', remote: false,
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

function seedModels(models: Array<Record<string, unknown>>) {
  const modelStore = useModelStore()
  modelStore.models = models as never
  modelStore.loaded = true
}

describe('pipeline store 多文件化', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    runnerCtor.mockClear()
    runnerStart.mockClear()
    runnerStartImpl = async () => {}
  })

  it('初始一個空白 doc；代理介面可讀寫；isBlankDoc 判準＝只有 input 根', () => {
    const s = usePipelineStore()
    expect(s.tabs).toHaveLength(1)
    expect(s.tabs[0].active).toBe(true)
    expect(s.isBlankDoc()).toBe(true)
    expect(s.isBlankDocId(s.tabs[0].id)).toBe(true)
    s.addToolNode('video.cut', { x: 0, y: 0 })
    expect(s.recipe.nodes.some(n => n.toolKey === 'video.cut')).toBe(true)
    expect(s.isBlankDoc()).toBe(false)
  })

  it('newDoc 開新分頁即 focus；每 doc 內容獨立；切回舊頁內容不互染', () => {
    const s = usePipelineStore()
    const firstId = s.tabs[0].id
    s.addToolNode('video.cut', { x: 0, y: 0 })
    const secondId = s.newDoc()
    expect(secondId).not.toBeNull()
    expect(s.activeDocId).toBe(secondId)
    expect(s.isBlankDoc()).toBe(true)                       // 新頁空白
    s.addToolNode('video.transcode', { x: 0, y: 0 })
    s.activeDocId = firstId                                  // 切回
    expect(s.recipe.nodes.some(n => n.toolKey === 'video.cut')).toBe(true)
    expect(s.recipe.nodes.some(n => n.toolKey === 'video.transcode')).toBe(false)
  })

  it('newDoc 滿 8 頁回 null', () => {
    const s = usePipelineStore()
    for (let i = 0; i < 7; i++) expect(s.newDoc()).not.toBeNull()   // 1 初始 + 7 = 8
    expect(s.tabs).toHaveLength(8)
    expect(s.newDoc()).toBeNull()
    expect(s.tabs).toHaveLength(8)
  })

  it('startRun 鎖：model-missing early return 後鎖已釋放、canRun 恢復（不鎖死全 app）', async () => {
    seedModels([{ family: 'gemma4', variant: '4b:Q4_K_M', downloaded: false }])
    const s = usePipelineStore()
    s.recipe = translateRecipe()
    s.inputFiles = [{ fileId: 'f1', filename: 'a.pdf' }]

    await s.startRun()

    expect(runnerCtor).not.toHaveBeenCalled()
    expect(s.runningDocId).toBeNull()          // 鎖已還
    expect(s.running).toBe(false)
    expect(s.canRun).toBe(true)                // 全域 gate 未殘留
    expect(s.errors.some(i => i.code === 'model_missing')).toBe(true)
  })

  it('checkModelsReady await 期間切分頁：model 錯誤寫回捕獲 doc、非切過去的 doc', async () => {
    const modelStore = useModelStore()
    modelStore.models = [{ family: 'gemma4', variant: '4b:Q4_K_M', downloaded: false }] as never
    modelStore.loaded = false
    let releaseEnsure!: () => void
    vi.spyOn(modelStore, 'ensureLoaded').mockImplementation(() => new Promise<void>((res) => {
      releaseEnsure = () => { modelStore.loaded = true; res() }
    }))

    const s = usePipelineStore()
    const docAId = s.tabs[0].id
    s.recipe = translateRecipe()
    s.inputFiles = [{ fileId: 'f1', filename: 'a.pdf' }]

    const runPromise = s.startRun()            // 卡在 ensureLoaded await
    const docBId = s.newDoc()                  // 期間切到新分頁 B
    expect(docBId).not.toBeNull()
    releaseEnsure()
    await runPromise

    // model_missing 應在 A（捕獲 doc），B（active）乾淨
    expect(s.activeDocId).toBe(docBId)
    expect(s.errors.some(i => i.code === 'model_missing')).toBe(false)   // B 視角
    s.activeDocId = docAId
    expect(s.errors.some(i => i.code === 'model_missing')).toBe(true)    // A 視角
    expect(s.runningDocId).toBeNull()
  })

  it('modelIssues per-doc：A 的 model_missing 不洩漏到 B 的 errors/issues', async () => {
    seedModels([{ family: 'gemma4', variant: '4b:Q4_K_M', downloaded: false }])
    const s = usePipelineStore()
    s.recipe = translateRecipe()
    s.inputFiles = [{ fileId: 'f1', filename: 'a.pdf' }]
    await s.startRun()                          // A 得 model_missing
    expect(s.errors.some(i => i.code === 'model_missing')).toBe(true)

    s.newDoc()                                  // B
    expect(s.issues.some(i => i.code === 'model_missing')).toBe(false)
  })

  it('重入鎖：run 進行中第二次 startRun 直接 return（runner 只建一次）；他分頁 canRun=false', async () => {
    seedModels([])
    const s = usePipelineStore()
    s.recipe = cutRecipe()
    s.inputFiles = [{ fileId: 'f1', filename: 'a.mp4' }]
    let finishRun!: () => void
    runnerStartImpl = () => new Promise<void>((res) => { finishRun = res })

    const p1 = s.startRun()
    expect(s.running).toBe(true)                // 同步鎖已生效（runner 建構前）
    void s.startRun()                           // double-click（鎖同步擋下）
    await vi.waitFor(() => expect(runnerStart).toHaveBeenCalled())
    expect(runnerCtor).toHaveBeenCalledTimes(1)

    const otherId = s.newDoc()                  // 跑中開/切他頁
    expect(otherId).not.toBeNull()
    s.recipe = cutRecipe()
    s.inputFiles = [{ fileId: 'f2', filename: 'b.mp4' }]
    expect(s.canRun).toBe(false)                // 全域一次一 run gate
    expect(s.running).toBe(false)               // 但 running 只屬跑中分頁

    finishRun()
    await p1
    expect(s.runningDocId).toBeNull()
    expect(s.canRun).toBe(true)
  })

  it('跑中切分頁：snapshot 寫回跑中 doc、不寫 active doc', async () => {
    seedModels([])
    const s = usePipelineStore()
    const docAId = s.tabs[0].id
    s.recipe = cutRecipe()
    s.inputFiles = [{ fileId: 'f1', filename: 'a.mp4' }]
    let finishRun!: () => void
    runnerStartImpl = () => new Promise<void>((res) => { finishRun = res })

    const p1 = s.startRun()
    await vi.waitFor(() => expect(runnerStart).toHaveBeenCalled())   // run 已起跑
    s.newDoc()                                  // 切走
    finishRun()
    await p1

    expect(s.runSnapshot).toBeNull()            // active（B）沒被灌
    s.activeDocId = docAId
    expect(s.runSnapshot?.status).toBe('completed')   // 終局寫回 A
  })
})
