/**
 * pipeline store — doc 生命週期＋.mtxflow 匯入/匯出 actions（spec §3/§5.3/§5.4、§8）。
 * PipelineRunner mock（同 modelGuard 手法）；openRecipeInTab 的 fetch 以 stubGlobal 假造。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const runnerCtor = vi.fn()
let runnerStartImpl: () => Promise<void> = async () => {}
const runnerStart = vi.fn(() => runnerStartImpl())
const runnerSnapshot = vi.fn(() => ({ status: 'completed', executions: [], truncatedNodes: [] }))
const runnerCancel = vi.fn(async () => {})

vi.mock('@/pipeline/runner', async () => {
  const actual = await vi.importActual<typeof import('@/pipeline/runner')>('@/pipeline/runner')
  class FakePipelineRunner {
    constructor(...args: unknown[]) { runnerCtor(...args) }
    start = runnerStart
    snapshot = runnerSnapshot
    cancel = runnerCancel
  }
  return { ...actual, PipelineRunner: FakePipelineRunner }
})

import { usePipelineStore } from '@/stores/pipeline'
import { useModelStore } from '@/stores/models'
import { serializeFlow, FLOW_FORMAT } from '@/pipeline/flowFile'
import type { Recipe } from '@/pipeline/types'

function cutRecipe(): Recipe {
  return {
    version: 1,
    name: 'r',
    nodes: [
      { id: 'input-1', kind: 'input', params: {}, position: { x: 0, y: 0 } },
      { id: 'n7-99', kind: 'tool', toolKey: 'video.cut', params: { start: 0, end: 1 }, position: { x: 100, y: 0 } },
    ],
    edges: [{ from: 'input-1', to: 'n7-99' }],
  }
}

describe('pipeline store — doc 生命週期與匯入/匯出', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    runnerCtor.mockClear()
    runnerStart.mockClear()
    runnerCancel.mockClear()
    runnerStartImpl = async () => {}
  })
  afterEach(() => { vi.unstubAllGlobals() })

  // ── closeDoc ────────────────────────────────────────────────────
  it('closeDoc：跑中 doc 拒關（回 false、doc 留存）', async () => {
    const modelStore = useModelStore()
    modelStore.models = [] as never
    modelStore.loaded = true
    const s = usePipelineStore()
    const runningId = s.tabs[0].id
    s.recipe = cutRecipe()
    s.inputFiles = [{ fileId: 'f1', filename: 'a.mp4' }]
    let finish!: () => void
    runnerStartImpl = () => new Promise<void>((res) => { finish = res })
    const p = s.startRun()
    await vi.waitFor(() => expect(runnerStart).toHaveBeenCalled())

    expect(s.closeDoc(runningId)).toBe(false)
    expect(s.tabs.some(x => x.id === runningId)).toBe(true)
    finish(); await p
  })

  it('closeDoc：關到 0 頁自動補一個空白分頁', () => {
    const s = usePipelineStore()
    const only = s.tabs[0].id
    expect(s.closeDoc(only)).toBe(true)
    expect(s.tabs).toHaveLength(1)
    expect(s.tabs[0].id).not.toBe(only)
    expect(s.isBlankDoc()).toBe(true)
  })

  it('closeDoc：關 active 分頁 focus 右鄰、末位則 focus 左鄰；關非 active 不動 focus', () => {
    const s = usePipelineStore()
    const a = s.tabs[0].id
    const b = s.newDoc()!
    const c = s.newDoc()!
    s.activeDocId = b
    s.closeDoc(b)                       // 中間、active → 右鄰 c
    expect(s.activeDocId).toBe(c)
    s.closeDoc(c)                       // 末位、active → 左鄰 a
    expect(s.activeDocId).toBe(a)
    const d = s.newDoc()!
    s.activeDocId = a
    s.closeDoc(d)                       // 非 active → focus 不變
    expect(s.activeDocId).toBe(a)
  })

  // ── renameDoc ───────────────────────────────────────────────────
  it('renameDoc 改分頁名（tabs 投影同步）', () => {
    const s = usePipelineStore()
    s.renameDoc(s.tabs[0].id, '我的流程')
    expect(s.tabs[0].name).toBe('我的流程')
  })

  // ── importRecipe ────────────────────────────────────────────────
  it('importRecipe：成功開新分頁、focus、信封 name 空時用 fallbackName、nodeSeq 重算不撞號', () => {
    const s = usePipelineStore()
    const firstId = s.tabs[0].id
    const text = serializeFlow('', cutRecipe())               // 信封 name 空
    const r = s.importRecipe(text, '拖進來的檔')
    expect(r.ok).toBe(true)
    expect(s.tabs).toHaveLength(2)
    expect(s.activeDocId).toBe(r.docId)
    expect(s.activeDocId).not.toBe(firstId)
    expect(s.tabs.find(x => x.id === r.docId)!.name).toBe('拖進來的檔')
    // nodeSeq 從 n7-99 重算 → 新增節點 id 前綴 > 7
    const newNodeId = s.addToolNode('video.transcode', { x: 0, y: 0 })
    expect(Number(/^n(\d+)-/.exec(newNodeId)![1])).toBeGreaterThan(7)
  })

  it('importRecipe：壞檔回錯誤、不開分頁；滿頁回 tab_limit', () => {
    const s = usePipelineStore()
    expect(s.importRecipe('{oops')).toEqual({ ok: false, error: 'bad_json' })
    expect(s.importRecipe(JSON.stringify({ format: FLOW_FORMAT, version: 99, name: '', recipe: { nodes: [], edges: [] } })))
      .toEqual({ ok: false, error: 'version_too_new' })
    expect(s.tabs).toHaveLength(1)
    for (let i = 0; i < 7; i++) s.newDoc()
    expect(s.importRecipe(serializeFlow('x', cutRecipe()))).toEqual({ ok: false, error: 'tab_limit' })
    expect(s.tabs).toHaveLength(8)
  })

  // ── rename 往返（spec §8 MUST）─────────────────────────────────
  it('rename 後 exportCurrent → importRecipe：信封/recipe/新 doc 名皆新名（不回退）', () => {
    const s = usePipelineStore()
    s.recipe = cutRecipe()                                    // recipe.name = 'r'（舊名）
    s.renameDoc(s.tabs[0].id, '改過的名')
    const text = s.exportCurrent()
    const env = JSON.parse(text)
    expect(env.name).toBe('改過的名')
    const r = s.importRecipe(text)
    expect(r.ok).toBe(true)
    expect(s.tabs.find(x => x.id === r.docId)!.name).toBe('改過的名')
    expect(s.recipe.name).toBe('改過的名')                    // 重建 Recipe 注入
  })

  // ── openRecipeInTab ─────────────────────────────────────────────
  it('openRecipeInTab：同 currentRecipeId 已開 → focus 不新開；未開 → 新分頁載入（名稱用 sqlite row name）', async () => {
    const graph = JSON.stringify(cutRecipe())
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({ id: 'r1', name: '常用A', graph }),
    })) as never)

    const s = usePipelineStore()
    const firstId = s.tabs[0].id
    s.addToolNode('video.cut', { x: 0, y: 0 })               // 讓第一頁非空

    const opened = await s.openRecipeInTab('r1')
    expect(opened).not.toBeNull()
    expect(opened).not.toBe(firstId)                          // 開了新分頁
    expect(s.tabs.find(x => x.id === opened)!.name).toBe('常用A')   // row name 優先
    expect(s.currentRecipeId).toBe('r1')

    s.activeDocId = firstId                                   // 切走再開同 id
    const again = await s.openRecipeInTab('r1')
    expect(again).toBe(opened)                                // focus 回原分頁、不新開
    expect(s.tabs).toHaveLength(2)
  })

  // ── adoptDraft（agent create_pipeline 用）───────────────────────
  it('adoptDraft：blank active 重用＝原地新文件（殘留關聯/錯誤/選檔全清）＋設名', () => {
    const s = usePipelineStore()
    const id = s.tabs[0].id
    // 弄髒 blank doc：殘留關聯與選檔（圖形仍 blank）
    s.currentRecipeId = 'stale-recipe'
    s.currentRunId = 'stale-run'
    s.inputFiles = [{ fileId: 'f0', filename: 'old.mp4' }]

    const r = s.adoptDraft(cutRecipe(), '草稿名')
    expect(r).toEqual({ ok: true, docId: id })                // 重用、沒開新頁
    expect(s.tabs).toHaveLength(1)
    expect(s.tabs[0].name).toBe('草稿名')
    expect(s.currentRecipeId).toBeNull()
    expect(s.currentRunId).toBeNull()
    expect(s.inputFiles).toHaveLength(0)
    expect(s.recipe.nodes.some(n => n.toolKey === 'video.cut')).toBe(true)
  })

  it('adoptDraft：非 blank → 開新分頁 focus-first、原頁不動；滿頁回 tab_limit_reached', () => {
    const s = usePipelineStore()
    const firstId = s.tabs[0].id
    s.addToolNode('video.transcode', { x: 0, y: 0 })          // 非 blank
    const before = JSON.stringify(s.recipe)

    const r = s.adoptDraft(cutRecipe(), '草稿')
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.docId).not.toBe(firstId)
    expect(s.activeDocId).toBe(r.docId)
    s.activeDocId = firstId
    expect(JSON.stringify(s.recipe)).toBe(before)             // 原頁未被蓋

    for (let i = 0; i < 6; i++) s.newDoc()                    // 滿 8
    expect(s.tabs).toHaveLength(8)
    s.activeDocId = firstId                                   // active 非 blank
    expect(s.adoptDraft(cutRecipe(), 'x')).toEqual({ ok: false, error: 'tab_limit_reached' })
  })

  // ── cancelRun 歸屬（Task 2 review N2 補測）──────────────────────
  it('cancelRun：跑中切分頁後 cancel，終局 snapshot 落跑中 doc、active 不被灌', async () => {
    const modelStore = useModelStore()
    modelStore.models = [] as never
    modelStore.loaded = true
    const s = usePipelineStore()
    const docAId = s.tabs[0].id
    s.recipe = cutRecipe()
    s.inputFiles = [{ fileId: 'f1', filename: 'a.mp4' }]
    let finish!: () => void
    runnerStartImpl = () => new Promise<void>((res) => { finish = res })
    const p = s.startRun()
    await vi.waitFor(() => expect(runnerStart).toHaveBeenCalled())

    s.newDoc()                                                // 切走
    await s.cancelRun()
    expect(runnerCancel).toHaveBeenCalled()
    expect(s.runSnapshot).toBeNull()                          // active(B) 乾淨
    s.activeDocId = docAId
    expect(s.runSnapshot).not.toBeNull()                      // 落回 A
    finish(); await p
  })

  // ── pendingImport ───────────────────────────────────────────────
  it('setPendingImport 存取（撿走即清由 view 負責，store 只存）', () => {
    const s = usePipelineStore()
    expect(s.pendingImport).toBeNull()
    s.setPendingImport({ text: 'abc', fallbackName: 'x' })
    expect(s.pendingImport).toEqual({ text: 'abc', fallbackName: 'x' })
    s.setPendingImport(null)
    expect(s.pendingImport).toBeNull()
  })
})
