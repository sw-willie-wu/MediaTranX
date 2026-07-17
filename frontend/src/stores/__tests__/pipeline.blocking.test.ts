/**
 * pipeline store 錯誤二分（blocking/advisory）＋可達子圖執行語意（spec F4-①）
 * ＋connect 前置驗證重構（F4-③）——2026-07-16 畫布 UX 批次 Task 2。
 * PipelineRunner 整套 mock（同 pipeline.multidoc.test.ts 手法）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const runnerCtor = vi.fn()
const runnerStart = vi.fn(async () => {})
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

/** 可跑主鏈（input→video.cut，無模型需求）＋一條帶錯的懸空鏈（unknown tool） */
function mixedRecipe(): Recipe {
  return {
    version: 1,
    name: 'r',
    nodes: [
      { id: 'input-1', kind: 'input', params: {}, position: { x: 0, y: 0 } },
      { id: 'a', kind: 'tool', toolKey: 'video.cut', params: { start: 0, end: 1 }, position: { x: 100, y: 0 } },
      { id: 'x', kind: 'tool', toolKey: 'nope.unknown', params: {}, position: { x: 0, y: 200 } },
      { id: 'y', kind: 'tool', toolKey: 'video.cut', params: { start: 0, end: 1 }, position: { x: 100, y: 200 } },
    ],
    edges: [
      { from: 'input-1', to: 'a' },
      { from: 'x', to: 'y' },       // 懸空鏈：x 未生根、x 是 unknown tool（error）
    ],
  }
}

function seedModels(models: Array<Record<string, unknown>>) {
  const modelStore = useModelStore()
  modelStore.models = models as never
  modelStore.loaded = true
}

describe('pipeline store 錯誤二分與可達子圖執行', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    runnerCtor.mockClear()
    runnerStart.mockClear()
  })

  it('懸空鏈上的 error 是 advisory、不擋 canRun；可達鏈乾淨即可跑', () => {
    const s = usePipelineStore()
    s.recipe = mixedRecipe()
    s.inputFiles = [{ fileId: 'f1', filename: 'a.mp4' }]
    expect(s.advisoryErrors.some(i => i.code === 'unknown_tool' && i.nodeId === 'x')).toBe(true)
    expect(s.blockingErrors).toHaveLength(0)
    expect(s.canRun).toBe(true)
  })

  it('可達鏈上的 error 是 blocking、鎖 canRun', () => {
    const s = usePipelineStore()
    const r = mixedRecipe()
    r.nodes.find(n => n.id === 'a')!.toolKey = 'nope.unknown'   // 錯誤移到可達鏈
    s.recipe = r
    s.inputFiles = [{ fileId: 'f1', filename: 'a.mp4' }]
    expect(s.blockingErrors.some(i => i.nodeId === 'a')).toBe(true)
    expect(s.canRun).toBe(false)
  })

  it('edge-scoped：懸空鏈上的 kind_mismatch（from 不可達）是 advisory、不擋 run', () => {
    const s = usePipelineStore()
    s.recipe = {
      version: 1, name: 'r',
      nodes: [
        { id: 'input-1', kind: 'input', params: {}, position: { x: 0, y: 0 } },
        { id: 'a', kind: 'tool', toolKey: 'video.cut', params: { start: 0, end: 1 }, position: { x: 100, y: 0 } },
        { id: 'x', kind: 'tool', toolKey: 'image.compress', params: {}, position: { x: 0, y: 200 } },
        { id: 'y', kind: 'tool', toolKey: 'video.cut', params: { start: 0, end: 1 }, position: { x: 100, y: 200 } },
      ],
      edges: [
        { from: 'input-1', to: 'a' },
        { from: 'x', to: 'y' },       // 懸空鏈上 image→video-only：kind_mismatch（edge-scoped）
      ],
    }
    s.inputFiles = [{ fileId: 'f1', filename: 'a.mp4' }]
    expect(s.advisoryErrors.some(i => i.code === 'kind_mismatch' && i.edge?.from === 'x')).toBe(true)
    expect(s.blockingErrors).toHaveLength(0)
    expect(s.canRun).toBe(true)
  })

  it('edge-scoped：可達鏈上的 kind_mismatch（from 可達）是 blocking、鎖 run', () => {
    const s = usePipelineStore()
    s.recipe = {
      version: 1, name: 'r',
      nodes: [
        { id: 'input-1', kind: 'input', params: {}, position: { x: 0, y: 0 } },
        { id: 'c', kind: 'tool', toolKey: 'image.compress', params: {}, position: { x: 100, y: 0 } },
        { id: 'd', kind: 'tool', toolKey: 'video.cut', params: { start: 0, end: 1 }, position: { x: 200, y: 0 } },
      ],
      edges: [{ from: 'input-1', to: 'c' }, { from: 'c', to: 'd' }],   // image→video-only 在可達鏈上
    }
    s.inputFiles = [{ fileId: 'f1', filename: 'a.png' }]
    expect(s.blockingErrors.some(i => i.code === 'kind_mismatch' && i.edge?.from === 'c')).toBe(true)
    expect(s.canRun).toBe(false)
  })

  it('graph-scoped（multi_root）一律 blocking，即使第二根未連通', () => {
    const s = usePipelineStore()
    const r = mixedRecipe()
    r.nodes = r.nodes.filter(n => n.id !== 'x' && n.id !== 'y')
    r.edges = r.edges.filter(e => e.from !== 'x')
    r.nodes.push({ id: 's2', kind: 'source', toolKey: 'video.download', params: { url: 'https://x' }, position: { x: 0, y: 300 } })
    s.recipe = r
    s.inputFiles = [{ fileId: 'f1', filename: 'a.mp4' }]
    expect(s.blockingErrors.some(i => i.code === 'multi_root')).toBe(true)
    expect(s.canRun).toBe(false)
  })

  it('modelIssues 不進二分：model_missing 在 errors、blockingErrors 為空、canRun 不受影響', async () => {
    seedModels([{ family: 'gemma4', variant: '4b:Q4_K_M', downloaded: false }])
    const s = usePipelineStore()
    s.recipe = {
      version: 1, name: 'r',
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
    s.inputFiles = [{ fileId: 'f1', filename: 'a.pdf' }]
    await s.startRun()
    expect(s.errors.some(i => i.code === 'model_missing')).toBe(true)
    expect(s.blockingErrors).toHaveLength(0)
    expect(s.canRun).toBe(true)                     // 既有語意不變：模型缺失不鎖執行鈕
  })

  it('checkModelsReady 只驗可達子圖：不可達節點缺模型不擋 run、不產 issue', async () => {
    seedModels([{ family: 'gemma4', variant: '4b:Q4_K_M', downloaded: false }])
    const s = usePipelineStore()
    s.recipe = {
      version: 1, name: 'r',
      nodes: [
        { id: 'input-1', kind: 'input', params: {}, position: { x: 0, y: 0 } },
        { id: 'a', kind: 'tool', toolKey: 'video.cut', params: { start: 0, end: 1 }, position: { x: 100, y: 0 } },
        {   // 孤立的 translate 節點（缺模型、不可達）
          id: 'lone', kind: 'tool', toolKey: 'document.translate',
          params: {
            source_language: 'en', target_language: 'zh-TW',
            model_family: 'gemma4', model_size: '4b', quantization: 'Q4_K_M', remote: false,
          },
          position: { x: 0, y: 200 },
        },
      ],
      edges: [{ from: 'input-1', to: 'a' }],
    }
    s.inputFiles = [{ fileId: 'f1', filename: 'a.mp4' }]
    await s.startRun()
    expect(s.errors.some(i => i.code === 'model_missing')).toBe(false)
    expect(runnerCtor).toHaveBeenCalledTimes(1)     // run 真的起跑
  })

  it('connect：成環被前置擋下、edges 無殘留（無「推入再回退」暫態）', () => {
    const s = usePipelineStore()
    s.recipe = {
      version: 1, name: 'r',
      nodes: [
        { id: 'input-1', kind: 'input', params: {}, position: { x: 0, y: 0 } },
        { id: 'a', kind: 'tool', toolKey: 'video.cut', params: { start: 0, end: 1 }, position: { x: 100, y: 0 } },
        { id: 'b', kind: 'tool', toolKey: 'video.cut', params: { start: 0, end: 1 }, position: { x: 200, y: 0 } },
      ],
      edges: [{ from: 'input-1', to: 'a' }, { from: 'a', to: 'b' }],
    }
    const err = s.connect('b', 'a')
    expect(err).toMatch(/cycle/)
    expect(s.recipe.edges).toHaveLength(2)
  })

  it('connect：匯流（in-degree 2）被前置擋下', () => {
    const s = usePipelineStore()
    s.recipe = {
      version: 1, name: 'r',
      nodes: [
        { id: 'input-1', kind: 'input', params: {}, position: { x: 0, y: 0 } },
        { id: 'a', kind: 'tool', toolKey: 'video.cut', params: { start: 0, end: 1 }, position: { x: 100, y: 0 } },
        { id: 'b', kind: 'tool', toolKey: 'video.cut', params: { start: 0, end: 1 }, position: { x: 100, y: 100 } },
      ],
      edges: [{ from: 'input-1', to: 'a' }, { from: 'input-1', to: 'b' }],
    }
    const err = s.connect('a', 'b')
    expect(err).toMatch(/in-degree/)
    expect(s.recipe.edges).toHaveLength(2)
  })

  it('connect：duplicate 維持靜默 no-op（回 null、不加邊）', () => {
    const s = usePipelineStore()
    s.recipe = {
      version: 1, name: 'r',
      nodes: [
        { id: 'input-1', kind: 'input', params: {}, position: { x: 0, y: 0 } },
        { id: 'a', kind: 'tool', toolKey: 'video.cut', params: { start: 0, end: 1 }, position: { x: 100, y: 0 } },
      ],
      edges: [{ from: 'input-1', to: 'a' }],
    }
    expect(s.connect('input-1', 'a')).toBeNull()
    expect(s.recipe.edges).toHaveLength(1)
  })

  it('connect：兩孤立 tool 相連合法（未生根子鏈可先組）', () => {
    const s = usePipelineStore()
    s.addToolNode('video.cut', { x: 0, y: 0 })
    s.addToolNode('video.cut', { x: 100, y: 0 })
    const [x, y] = s.recipe.nodes.filter(n => n.kind === 'tool').map(n => n.id)
    expect(s.connect(x, y)).toBeNull()
    expect(s.recipe.edges.some(e => e.from === x && e.to === y)).toBe(true)
  })
})
