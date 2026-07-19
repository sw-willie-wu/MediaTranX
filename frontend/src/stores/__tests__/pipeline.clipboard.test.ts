/**
 * pipeline store 剪貼簿 copy/paste（spec F3 複製貼上）——2026-07-16 畫布 UX
 * 批次 Task 4。根排除、內部邊重接、nodeSeq 配號、跨 doc、連貼偏移、
 * 單一 undo 步、running 禁用、深拷貝隔離。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

let runnerStartImpl: () => Promise<void> = async () => {}
const runnerStart = vi.fn(() => runnerStartImpl())

vi.mock('@/pipeline/runner', async () => {
  const actual = await vi.importActual<typeof import('@/pipeline/runner')>('@/pipeline/runner')
  class FakePipelineRunner {
    start = runnerStart
    snapshot = vi.fn(() => ({ status: 'completed', executions: [], truncatedNodes: [] }))
    cancel = vi.fn(async () => {})
  }
  return { ...actual, PipelineRunner: FakePipelineRunner }
})

import { usePipelineStore } from '@/stores/pipeline'
import { useModelStore } from '@/stores/models'

/** 建立 input→a→b 直鏈，回傳 [aId, bId] */
function seedChain(s: ReturnType<typeof usePipelineStore>): [string, string] {
  const a = s.addToolNode('video.cut', { x: 100, y: 50 })
  const b = s.addToolNode('video.transcode', { x: 300, y: 50 })
  s.connect('input-1', a)
  s.connect(a, b)
  return [a, b]
}

describe('pipeline store 剪貼簿', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    runnerStartImpl = async () => {}
    runnerStart.mockClear()
  })

  it('copy 排除 input/source 根；只複製 tool 節點', () => {
    const s = usePipelineStore()
    const [a] = seedChain(s)
    expect(s.copyNodes(['input-1', a])).toBe(1)
    const pasted = s.pasteNodes()
    expect(pasted).toHaveLength(1)
    expect(s.recipe.nodes.filter(n => n.kind === 'input')).toHaveLength(1)   // 根不重複
  })

  it('copy 排除 source 根（同 input 根待遇）', () => {
    const s = usePipelineStore()
    const srcId = s.addToolNode('video.download', { x: 0, y: 0 })   // source 節點（取代 input 根）
    const a = s.addToolNode('video.cut', { x: 200, y: 0 })
    expect(s.recipe.nodes.find(n => n.id === srcId)?.kind).toBe('source')
    expect(s.copyNodes([srcId, a])).toBe(1)           // source 不入剪貼簿
    const pasted = s.pasteNodes()!
    expect(pasted).toHaveLength(1)
    expect(s.recipe.nodes.filter(n => n.kind === 'source')).toHaveLength(1)   // 根不重複
  })

  it('選取集合內部邊重接到新 id；外部邊（連到根）捨棄', () => {
    const s = usePipelineStore()
    const [a, b] = seedChain(s)
    expect(s.copyNodes([a, b])).toBe(2)
    const pasted = s.pasteNodes()!
    expect(pasted).toHaveLength(2)
    const [na, nb] = pasted
    expect(s.recipe.edges.some(e => e.from === na && e.to === nb)).toBe(true)   // 內部邊重接
    expect(s.recipe.edges.some(e => e.from === 'input-1' && e.to === na)).toBe(false)   // 外部邊不帶
    // 貼上的是未生根子鏈：合法（tool_unrooted warning、非 error）
    expect(s.blockingErrors).toHaveLength(0)
  })

  it('同 doc 連貼：id 全不撞、位置逐次 +32 錯開', () => {
    const s = usePipelineStore()
    const [a] = seedChain(s)
    const srcPos = s.recipe.nodes.find(n => n.id === a)!.position!
    s.copyNodes([a])
    const p1 = s.pasteNodes()!
    const p2 = s.pasteNodes()!
    const ids = new Set([...s.recipe.nodes.map(n => n.id)])
    expect(ids.size).toBe(s.recipe.nodes.length)                     // 無撞號
    const n1 = s.recipe.nodes.find(n => n.id === p1[0])!
    const n2 = s.recipe.nodes.find(n => n.id === p2[0])!
    expect(n1.position).toEqual({ x: srcPos.x + 32, y: srcPos.y + 32 })
    expect(n2.position).toEqual({ x: srcPos.x + 64, y: srcPos.y + 64 })
  })

  it('跨分頁貼上：剪貼簿跨 doc 有效、目標 doc 配號不撞、來源 doc 不動', () => {
    const s = usePipelineStore()
    const firstId = s.tabs[0].id
    const [a, b] = seedChain(s)
    const beforeNodes = s.recipe.nodes.length
    s.copyNodes([a, b])
    s.newDoc()
    const pasted = s.pasteNodes()!
    expect(pasted).toHaveLength(2)
    expect(s.recipe.nodes.filter(n => n.kind === 'tool')).toHaveLength(2)   // B 頁收到
    const idsB = new Set(s.recipe.nodes.map(n => n.id))
    expect(idsB.size).toBe(s.recipe.nodes.length)
    s.activeDocId = firstId
    expect(s.recipe.nodes).toHaveLength(beforeNodes)                        // A 頁不動
  })

  it('貼上＝單一 undo 步（節點與內部邊一次退光）', () => {
    const s = usePipelineStore()
    const [a, b] = seedChain(s)
    s.copyNodes([a, b])
    const nodesBefore = s.recipe.nodes.length
    const edgesBefore = s.recipe.edges.length
    s.pasteNodes()
    expect(s.recipe.nodes.length).toBe(nodesBefore + 2)
    s.undo()
    expect(s.recipe.nodes.length).toBe(nodesBefore)
    expect(s.recipe.edges.length).toBe(edgesBefore)
  })

  it('params/keepOutput 深拷貝：貼上後改原節點不影響剪貼簿再貼', () => {
    const s = usePipelineStore()
    const [a] = seedChain(s)
    s.updateNodeParams(a, { start: 0, end: 7 })
    s.setKeepOutput(a, true)
    s.copyNodes([a])
    s.updateNodeParams(a, { start: 0, end: 99 })     // 複製後改原節點
    const pasted = s.pasteNodes()!
    const n = s.recipe.nodes.find(x => x.id === pasted[0])!
    expect(n.params.end).toBe(7)                      // 剪貼簿存的是複製當下
    expect(n.keepOutput).toBe(true)
  })

  it('執行中 paste 回 null；空剪貼簿 paste 回 null；空選取 copy 回 0', async () => {
    const modelStore = useModelStore()
    modelStore.models = [] as never
    modelStore.loaded = true
    const s = usePipelineStore()
    expect(s.pasteNodes()).toBeNull()                 // 空剪貼簿
    expect(s.copyNodes([])).toBe(0)
    expect(s.copyNodes(['input-1'])).toBe(0)          // 只有根 → 0
    const [a] = seedChain(s)
    s.copyNodes([a])
    s.inputFiles = [{ fileId: 'f1', filename: 'a.mp4' }]
    let release!: () => void
    runnerStartImpl = () => new Promise<void>((res) => { release = res })
    const run = s.startRun()
    await vi.waitFor(() => expect(runnerStart).toHaveBeenCalled())
    expect(s.pasteNodes()).toBeNull()                 // 執行中
    release()
    await run
    expect(s.pasteNodes()).not.toBeNull()             // 跑完恢復
  })
})
