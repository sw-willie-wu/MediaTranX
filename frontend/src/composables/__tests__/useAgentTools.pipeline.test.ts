/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * agent pipeline 工具 × 多分頁 store（spec §5.4、Task 7）。
 * 獨立檔：需要 PipelineRunner mock（主 useAgentTools.test.ts 不 mock runner）。
 */
// @vitest-environment jsdom

import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { describe, it, expect, beforeEach, vi } from 'vitest'

let runnerStartImpl: () => Promise<void> = async () => {}
const runnerStart = vi.fn(() => runnerStartImpl())
vi.mock('@/pipeline/runner', async () => {
  const actual = await vi.importActual<typeof import('@/pipeline/runner')>('@/pipeline/runner')
  class FakePipelineRunner {
    start = runnerStart
    snapshot = vi.fn(() => ({ status: 'running', executions: [], truncatedNodes: [] }))
    cancel = vi.fn(async () => {})
  }
  return { ...actual, PipelineRunner: FakePipelineRunner }
})

import { dispatch, type ToolCall } from '@/composables/useAgentTools'
import { usePipelineStore } from '@/stores/pipeline'
import { useModelStore } from '@/stores/models'
import type { RunSnapshot } from '@/pipeline/runner'

function makeRouter() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div/>' } },
      { path: '/pipeline', component: { template: '<div/>' } },
    ],
  })
  router.push('/')
  return router
}

async function withContext(router: ReturnType<typeof makeRouter>, fn: (d: typeof dispatch) => Promise<any>): Promise<any> {
  await router.isReady()
  let result: any
  const Comp = defineComponent({
    async setup() { result = await fn(dispatch); return {} },
    template: '<div></div>',
  })
  mount(Comp, { global: { plugins: [router] } })
  // create_pipeline 內有多輪 dynamic import＋router.push，單一 tick 不夠；
  // 首案在全套平行 worker 負載下可近 1s，timeout 放寬防 flake
  await vi.waitFor(() => { if (result === undefined) throw new Error('setup pending') }, { timeout: 5000 })
  return result
}

function tc(name: string, args: object = {}): ToolCall {
  return { id: 'tc-' + name, type: 'function', function: { name, arguments: JSON.stringify(args) } }
}

const DRAFT = {
  name: '草稿線',
  nodes: [
    { id: 'input-1', kind: 'input' },
    { id: 'n2', kind: 'tool', tool_key: 'video.cut', params: {} },
  ],
  edges: [{ from: 'input-1', to: 'n2' }],
}

beforeEach(() => {
  setActivePinia(createPinia())
  runnerStart.mockClear()
  runnerStartImpl = async () => {}
})

describe('agent pipeline 工具 × 多分頁', () => {
  it('create_pipeline：非 blank active → 開新分頁 focus＋設名，原頁不被蓋', async () => {
    const router = makeRouter()
    const s = usePipelineStore()
    const firstId = s.tabs[0].id
    s.addToolNode('video.transcode', { x: 0, y: 0 })
    const before = JSON.stringify(s.recipe)

    const result = await withContext(router, d => d(tc('create_pipeline', DRAFT)))
    expect(result.ok).toBe(true)
    expect(s.tabs).toHaveLength(2)
    expect(s.activeDocId).not.toBe(firstId)
    expect(s.tabs.find(x => x.active)!.name).toBe('草稿線')
    expect(s.recipe.nodes.some(n => n.toolKey === 'video.cut')).toBe(true)
    s.activeDocId = firstId
    expect(JSON.stringify(s.recipe)).toBe(before)          // 原頁未被蓋
  })

  it('create_pipeline：blank active 重用＋清殘留關聯', async () => {
    const router = makeRouter()
    const s = usePipelineStore()
    s.currentRecipeId = 'stale'
    s.currentRunId = 'stale-run'

    const result = await withContext(router, d => d(tc('create_pipeline', DRAFT)))
    expect(result.ok).toBe(true)
    expect(s.tabs).toHaveLength(1)                          // 重用、沒開新頁
    expect(s.currentRecipeId).toBeNull()
    expect(s.currentRunId).toBeNull()
  })

  it('create_pipeline：他分頁跑中也不擋（舊 busy gate 已移除——草稿走新分頁永遠安全）', async () => {
    const router = makeRouter()
    const modelStore = useModelStore()
    modelStore.models = [] as never
    modelStore.loaded = true
    const s = usePipelineStore()
    const blankId = s.tabs[0].id
    // doc B：起跑後掛住
    s.newDoc()
    s.addToolNode('video.cut', { x: 200, y: 0 })
    s.connect('input-1', s.recipe.nodes.find(n => n.toolKey === 'video.cut')!.id)
    s.inputFiles = [{ fileId: 'f1', filename: 'a.mp4' }]
    let finish!: () => void
    runnerStartImpl = () => new Promise<void>((res) => { finish = res })
    const p = s.startRun()
    await vi.waitFor(() => expect(runnerStart).toHaveBeenCalled())

    s.activeDocId = blankId                                 // 切回空白頁（B 還在跑）
    const result = await withContext(router, d => d(tc('create_pipeline', DRAFT)))
    expect(result.ok).toBe(true)                            // 不回 pipeline_busy
    expect(s.tabs.find(x => x.active)!.name).toBe('草稿線')

    finish(); await p
  })

  it('create_pipeline：滿 8 頁且 active 非 blank → tool_failed(tab_limit_reached)、docs 不變', async () => {
    const router = makeRouter()
    const s = usePipelineStore()
    s.addToolNode('video.transcode', { x: 0, y: 0 })
    while (s.tabs.length < 8) {
      const id = s.newDoc()!
      s.addToolNode('video.transcode', { x: 0, y: 0 })      // 全部弄非 blank
      void id
    }
    const result = await withContext(router, d => d(tc('create_pipeline', DRAFT)))
    expect(result.error).toBe('agent.error.tool_failed')
    expect(result.detail).toBe('tab_limit_reached')
    expect(s.tabs).toHaveLength(8)
  })

  it('get_task_status(run_id)：使用者切走分頁後仍查得到（跨 doc 解析）', async () => {
    const router = makeRouter()
    const s = usePipelineStore()
    s.currentRunId = 'run-abc'
    s.runSnapshot = {
      status: 'running',
      executions: [{ nodeId: 'n2', status: 'completed' } as never],
      truncatedNodes: [],
    } as RunSnapshot
    s.newDoc()                                              // 切到別頁

    const result = await withContext(router, d => d(tc('get_task_status', { run_id: 'run-abc' })))
    expect(result.ok).toBe(true)
    expect(result.run.run_id).toBe('run-abc')
    expect(result.run.done).toBe(1)

    const miss = await withContext(router, d => d(tc('get_task_status', { run_id: 'run-nope' })))
    expect(miss.error).toBe('agent.error.tool_failed')
  })

  it('run_pipeline：另一分頁在跑（runningDocId 非 null）→ pipeline_busy', async () => {
    const router = makeRouter()
    const modelStore = useModelStore()
    modelStore.models = [] as never
    modelStore.loaded = true
    const s = usePipelineStore()
    // doc A：可跑的圖＋輸入檔，起跑後掛住
    s.addToolNode('video.cut', { x: 200, y: 0 })
    s.connect('input-1', s.recipe.nodes.find(n => n.toolKey === 'video.cut')!.id)
    s.inputFiles = [{ fileId: 'f1', filename: 'a.mp4' }]
    let finish!: () => void
    runnerStartImpl = () => new Promise<void>((res) => { finish = res })
    const p = s.startRun()
    await vi.waitFor(() => expect(runnerStart).toHaveBeenCalled())

    s.newDoc()                                              // 切到 doc B
    const result = await withContext(router, d => d(tc('run_pipeline', {})))
    expect(result.error).toBe('agent.error.pipeline_busy')

    finish(); await p
  })
})
