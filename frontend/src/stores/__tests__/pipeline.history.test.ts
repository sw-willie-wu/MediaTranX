/**
 * pipeline store undo/redo 歷史（spec F3）——2026-07-16 畫布 UX 批次 Task 3。
 * per-doc past/future 快照堆疊、mutation push、參數/移動 800ms 合併窗、
 * cap 50、running 禁用、hydrate 清史、序列化隔離。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const runnerCtor = vi.fn()
let runnerStartImpl: () => Promise<void> = async () => {}
const runnerStart = vi.fn(() => runnerStartImpl())

vi.mock('@/pipeline/runner', async () => {
  const actual = await vi.importActual<typeof import('@/pipeline/runner')>('@/pipeline/runner')
  class FakePipelineRunner {
    constructor(...args: unknown[]) { runnerCtor(...args) }
    start = runnerStart
    snapshot = vi.fn(() => ({ status: 'completed', executions: [], truncatedNodes: [] }))
    cancel = vi.fn(async () => {})
  }
  return { ...actual, PipelineRunner: FakePipelineRunner }
})

import { usePipelineStore } from '@/stores/pipeline'
import { useModelStore } from '@/stores/models'
import { serializeFlow } from '@/pipeline/flowFile'

describe('pipeline store undo/redo 歷史', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('加節點可 undo/redo；titlebar 可用態（canUndo/canRedo）同步', () => {
    const s = usePipelineStore()
    expect(s.canUndo).toBe(false)
    s.addToolNode('video.cut', { x: 0, y: 0 })
    expect(s.canUndo).toBe(true)
    expect(s.canRedo).toBe(false)
    s.undo()
    expect(s.recipe.nodes.some(n => n.kind === 'tool')).toBe(false)
    expect(s.canUndo).toBe(false)
    expect(s.canRedo).toBe(true)
    s.redo()
    expect(s.recipe.nodes.some(n => n.toolKey === 'video.cut')).toBe(true)
    expect(s.canRedo).toBe(false)
  })

  it('connect/setKeepOutput 各為一步；undo 逐步回退', () => {
    const s = usePipelineStore()
    const a = s.addToolNode('video.cut', { x: 0, y: 0 })
    s.connect('input-1', a)
    s.setKeepOutput(a, true)
    expect(s.recipe.nodes.find(n => n.id === a)?.keepOutput).toBe(true)
    s.undo()   // keepOutput
    expect(s.recipe.nodes.find(n => n.id === a)?.keepOutput).toBeUndefined()
    s.undo()   // connect
    expect(s.recipe.edges).toHaveLength(0)
    s.undo()   // addToolNode
    expect(s.recipe.nodes.some(n => n.kind === 'tool')).toBe(false)
  })

  it('disconnect 可 undo（邊復原）；no-op disconnect 不進歷史', () => {
    const s = usePipelineStore()
    const a = s.addToolNode('video.cut', { x: 0, y: 0 })
    s.connect('input-1', a)
    s.disconnect('input-1', a)
    expect(s.recipe.edges).toHaveLength(0)
    s.undo()
    expect(s.recipe.edges).toEqual([{ from: 'input-1', to: a }])
    s.disconnect('input-1', 'nope')        // 不存在的邊 → no-op
    expect(s.canRedo).toBe(true)           // no-op 不 push：future 未被清（push 會清 future）
    const before = s.recipe.edges.length
    s.undo()                               // 應退 connect 那步、非 no-op 空步
    expect(s.recipe.edges.length).toBe(before - 1)
  })

  it('removeNode 可 undo（節點與邊一併復原）', () => {
    const s = usePipelineStore()
    const a = s.addToolNode('video.cut', { x: 0, y: 0 })
    s.connect('input-1', a)
    s.removeNode(a)
    expect(s.recipe.nodes.some(n => n.id === a)).toBe(false)
    expect(s.recipe.edges).toHaveLength(0)
    s.undo()
    expect(s.recipe.nodes.some(n => n.id === a)).toBe(true)
    expect(s.recipe.edges).toEqual([{ from: 'input-1', to: a }])
  })

  it('connect 失敗/duplicate 不進歷史', () => {
    const s = usePipelineStore()
    const a = s.addToolNode('video.cut', { x: 0, y: 0 })
    s.connect('input-1', a)
    const steps = () => {
      // 以 undo 到底的次數計步（間接觀測 past 深度）
      let n = 0
      while (s.canUndo) { s.undo(); n++ }
      while (s.canRedo) s.redo()
      return n
    }
    const before = steps()
    s.connect('input-1', a)          // duplicate → 靜默 no-op
    s.connect(a, 'input-1')          // 成環 → 前置擋下
    expect(steps()).toBe(before)
  })

  it('同節點連續 updateNodeParams 在 800ms 窗內合併為一步；逾窗分步', () => {
    const s = usePipelineStore()
    const a = s.addToolNode('video.cut', { x: 0, y: 0 })
    s.updateNodeParams(a, { start: 0, end: 1 })   // 基準步
    vi.advanceTimersByTime(1000)                   // 斷窗
    s.updateNodeParams(a, { start: 0, end: 2 })   // 新步（快照＝end:1）
    vi.advanceTimersByTime(300)
    s.updateNodeParams(a, { start: 0, end: 3 })   // 窗內 → 與上一步合併
    s.undo()                                       // 一步退掉兩次編輯
    expect(s.recipe.nodes.find(n => n.id === a)?.params.end).toBe(1)
    s.redo()
    expect(s.recipe.nodes.find(n => n.id === a)?.params.end).toBe(3)
    vi.advanceTimersByTime(1000)                   // 逾窗
    s.updateNodeParams(a, { start: 0, end: 5 })
    s.undo()
    expect(s.recipe.nodes.find(n => n.id === a)?.params.end).toBe(3)   // 只退最後一步
  })

  it('異類 mutation 介入會斷開合併窗', () => {
    const s = usePipelineStore()
    const a = s.addToolNode('video.cut', { x: 0, y: 0 })
    s.updateNodeParams(a, { start: 1, end: 2 })
    s.addToolNode('video.transcode', { x: 200, y: 0 })   // 異類介入
    s.updateNodeParams(a, { start: 1, end: 9 })          // 雖在 800ms 內，仍是新步
    s.undo()
    expect(s.recipe.nodes.find(n => n.id === a)?.params.end).toBe(2)
  })

  it('moveNodes：一次拖曳（含多節點）＝一步；同集合 800ms 內合併；moveNode 委派相容', () => {
    const s = usePipelineStore()
    const a = s.addToolNode('video.cut', { x: 0, y: 0 })
    const b = s.addToolNode('video.transcode', { x: 200, y: 0 })
    s.moveNodes([{ id: a, position: { x: 10, y: 10 } }, { id: b, position: { x: 210, y: 10 } }])
    vi.advanceTimersByTime(300)
    s.moveNodes([{ id: a, position: { x: 20, y: 20 } }, { id: b, position: { x: 220, y: 20 } }])   // 合併
    s.undo()   // 一步退回拖曳前
    expect(s.recipe.nodes.find(n => n.id === a)?.position).toEqual({ x: 0, y: 0 })
    // moveNode 舊 API 委派：仍可用、單節點一步
    s.moveNode(a, { x: 50, y: 50 })
    expect(s.recipe.nodes.find(n => n.id === a)?.position).toEqual({ x: 50, y: 50 })
    s.undo()
    expect(s.recipe.nodes.find(n => n.id === a)?.position).toEqual({ x: 0, y: 0 })
  })

  it('undo 後新 mutation 清空 future（不可 redo 回被覆寫的分支）', () => {
    const s = usePipelineStore()
    s.addToolNode('video.cut', { x: 0, y: 0 })
    s.undo()
    expect(s.canRedo).toBe(true)
    s.addToolNode('video.transcode', { x: 0, y: 0 })
    expect(s.canRedo).toBe(false)
  })

  it('undo/redo 也會斷開合併窗（快照不錯位）', () => {
    const s = usePipelineStore()
    const a = s.addToolNode('video.cut', { x: 0, y: 0 })
    s.updateNodeParams(a, { start: 1, end: 2 })
    s.undo()                                        // params 步退掉
    s.redo()
    s.updateNodeParams(a, { start: 1, end: 7 })     // 窗理應已斷 → 新步
    s.undo()
    expect(s.recipe.nodes.find(n => n.id === a)?.params.end).toBe(2)
  })

  it('歷史深度 cap 50：超過丟最舊', () => {
    const s = usePipelineStore()
    const a = s.addToolNode('video.cut', { x: 0, y: 0 })
    for (let i = 1; i <= 60; i++) {
      vi.advanceTimersByTime(1000)                  // 每次逾窗 → 各自一步
      s.updateNodeParams(a, { start: 0, end: i })
    }
    let n = 0
    while (s.canUndo) { s.undo(); n++ }
    expect(n).toBe(50)
    // 最舊的步已被丟棄：退到底不是初始空畫布，而是中途狀態
    expect(s.recipe.nodes.some(n2 => n2.id === a)).toBe(true)
  })

  it('選取節點被 undo 移除時 selectedNodeId 收斂', () => {
    const s = usePipelineStore()
    const a = s.addToolNode('video.cut', { x: 0, y: 0 })
    s.selectedNodeId = a
    s.undo()
    expect(s.selectedNodeId).toBeNull()
  })

  it('per-doc 隔離：A 頁歷史不受 B 頁操作影響；切 doc 斷合併窗', () => {
    const s = usePipelineStore()
    const first = s.tabs[0].id
    const a = s.addToolNode('video.cut', { x: 0, y: 0 })
    s.updateNodeParams(a, { start: 1, end: 2 })
    s.newDoc()
    s.addToolNode('video.transcode', { x: 0, y: 0 })
    expect(s.canUndo).toBe(true)
    s.undo()
    expect(s.recipe.nodes.some(n => n.kind === 'tool')).toBe(false)   // 只退 B 頁
    s.activeDocId = first
    expect(s.recipe.nodes.find(n => n.id === a)?.params.end).toBe(2)  // A 頁完好
    s.updateNodeParams(a, { start: 1, end: 9 })   // 切回後窗已斷 → 新步
    s.undo()
    expect(s.recipe.nodes.find(n => n.id === a)?.params.end).toBe(2)
  })

  it('adoptDraft（hydrate 路徑）清歷史', () => {
    const s = usePipelineStore()
    s.addToolNode('video.cut', { x: 0, y: 0 })
    s.undo()                                       // recipe 回空白、future 有一步
    expect(s.isBlankDoc()).toBe(true)
    expect(s.canRedo).toBe(true)
    const r = s.adoptDraft({
      version: 1, name: 'agent',
      nodes: [
        { id: 'input-1', kind: 'input', params: {} },
        { id: 'n2', kind: 'tool', toolKey: 'video.cut', params: { start: 0, end: 1 } },
      ],
      edges: [{ from: 'input-1', to: 'n2' }],
    }, 'agent')
    expect(r.ok).toBe(true)
    expect(s.canUndo).toBe(false)
    expect(s.canRedo).toBe(false)
  })

  it('執行中 canUndo/canRedo 為 false、undo/redo no-op', async () => {
    const modelStore = useModelStore()
    modelStore.models = [] as never
    modelStore.loaded = true
    const s = usePipelineStore()
    const a = s.addToolNode('video.cut', { x: 0, y: 0 })
    s.updateNodeParams(a, { start: 0, end: 1 })
    s.connect('input-1', a)
    s.inputFiles = [{ fileId: 'f1', filename: 'a.mp4' }]
    let release!: () => void
    runnerStartImpl = () => new Promise<void>((res) => { release = res })
    const run = s.startRun()
    await vi.advanceTimersByTimeAsync(0)           // flush startRun 的 async 前段直到 runner.start
    expect(runnerStart).toHaveBeenCalled()
    expect(s.running).toBe(true)
    expect(s.canUndo).toBe(false)
    const edges = s.recipe.edges.length
    s.undo()
    expect(s.recipe.edges.length).toBe(edges)      // no-op
    release()
    await run
    expect(s.canUndo).toBe(true)                   // 跑完恢復
  })

  it('序列化隔離：exportCurrent/saveCurrent payload 不含 history', () => {
    const s = usePipelineStore()
    s.addToolNode('video.cut', { x: 0, y: 0 })
    const exported = JSON.parse(s.exportCurrent())
    expect(JSON.stringify(exported)).not.toContain('history')
    // saveCurrent 的 graph payload＝JSON.stringify(recipe)——同構驗證
    expect(JSON.stringify(s.recipe)).not.toContain('history')
    // flowFile 序列化亦然
    expect(serializeFlow('t', s.recipe)).not.toContain('history')
  })
})
