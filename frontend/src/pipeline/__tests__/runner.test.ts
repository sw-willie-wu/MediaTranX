import { describe, it, expect, vi } from 'vitest'
import { PipelineRunner, type EngineDeps } from '../runner'
import type { Recipe, ToolSpec } from '../types'

const REG: Record<string, ToolSpec> = {
  'video.download': {
    toolKey: 'video.download', apiPath: '/video/download', labelKey: 'x', kind: 'source',
    inputKinds: [], outputKind: () => 'video',
    paramSchema: [{ name: 'url', type: 'string' }],
  },
  'video.transcode': {
    toolKey: 'video.transcode', apiPath: '/video/transcode', labelKey: 'x', kind: 'tool',
    inputKinds: ['video'], outputKind: (p) => (p.output_format === 'gif' ? 'image' : 'video'),
    paramSchema: [{ name: 'output_format', type: 'enum', options: ['mp4', 'gif'], default: 'mp4' }],
  },
  'image.compress': {
    toolKey: 'image.compress', apiPath: '/image/compress', labelKey: 'x', kind: 'tool',
    inputKinds: ['image'], outputKind: () => 'image',
    paramSchema: [{ name: 'strength', type: 'number', default: 60 }],
  },
  'document.split': {
    toolKey: 'document.split', apiPath: '/document/split', labelKey: 'x', kind: 'tool',
    inputKinds: ['document'], outputKind: () => 'document',
    paramSchema: [{ name: 'pages', type: 'string', default: '' }],
  },
}

/** 手動決議的 fake deps:submit 記錄呼叫、complete()/fail() 觸發 terminal callback */
function makeDeps(maxInFlight = 4) {
  const submitted: Array<{ apiPath: string; params: Record<string, unknown>; taskId: string }> = []
  const callbacks = new Map<string, (t: { status: string; result: unknown }) => void>()
  const cancelled: string[] = []
  let seq = 0
  const deps: EngineDeps = {
    submit: vi.fn(async (apiPath, params) => {
      const taskId = `t${++seq}`
      submitted.push({ apiPath, params, taskId })
      return taskId
    }),
    onTaskTerminal: (taskId, cb) => { callbacks.set(taskId, cb) },
    cancel: vi.fn(async (taskId: string) => { cancelled.push(taskId) }),
    maxInFlight: () => maxInFlight,
  }
  return {
    deps, submitted, cancelled,
    complete(taskId: string, result: unknown = {}) { callbacks.get(taskId)?.({ status: 'completed', result }) },
    fail(taskId: string) { callbacks.get(taskId)?.({ status: 'failed', result: null }) },
  }
}

const flush = () => new Promise<void>((r) => setTimeout(r, 0))

function chainRecipe(): Recipe {
  return {
    version: 1, name: 'chain',
    nodes: [
      { id: 'in', kind: 'input', params: {} },
      { id: 'tc', kind: 'tool', toolKey: 'video.transcode', params: { output_format: 'gif' } },
      { id: 'cp', kind: 'tool', toolKey: 'image.compress', params: {} },
    ],
    edges: [{ from: 'in', to: 'tc' }, { from: 'tc', to: 'cp' }],
  }
}

describe('PipelineRunner', () => {
  it('runs a straight chain, feeding output_file_id downstream', async () => {
    const h = makeDeps()
    const r = new PipelineRunner(chainRecipe(), REG, h.deps, { inputFileIds: ['f1'] })
    const doneP = r.start()
    await flush()
    expect(h.submitted).toHaveLength(1)
    expect(h.submitted[0].apiPath).toBe('/video/transcode')
    expect(h.submitted[0].params.file_id).toBe('f1')
    expect(h.submitted[0].params.suppress_results).toBe(true)   // 非末端

    h.complete('t1', { output_file_id: 'g1' })
    await flush()
    expect(h.submitted).toHaveLength(2)
    expect(h.submitted[1].apiPath).toBe('/image/compress')
    expect(h.submitted[1].params.file_id).toBe('g1')
    expect(h.submitted[1].params.suppress_results).toBe(false)  // 末端

    h.complete('t2', { output_file_id: 'c1' })
    await doneP
    const snap = r.snapshot()
    expect(snap.status).toBe('completed')
    expect(snap.executions.every(e => e.status === 'completed')).toBe(true)
  })

  it('fans out N input files independently; failure skips only that branch', async () => {
    const h = makeDeps()
    const r = new PipelineRunner(chainRecipe(), REG, h.deps, { inputFileIds: ['f1', 'f2'] })
    const doneP = r.start()
    await flush()
    expect(h.submitted).toHaveLength(2)   // 兩檔各自 transcode

    h.fail(h.submitted[0].taskId)          // f1 的 transcode 失敗
    h.complete(h.submitted[1].taskId, { output_file_id: 'g2' })
    await flush()
    // f1 分支下游 skipped、f2 分支 compress 提交
    expect(h.submitted).toHaveLength(3)
    expect(h.submitted[2].params.file_id).toBe('g2')

    h.complete(h.submitted[2].taskId, { output_file_id: 'c2' })
    await doneP
    const snap = r.snapshot()
    expect(snap.status).toBe('completed_with_errors')
    expect(snap.executions.some(e => e.status === 'skipped')).toBe(true)
  })

  it('multi-output upstream fans out downstream per output (cap 32)', async () => {
    const h = makeDeps(64)   // in-flight cap 拉高,單測聚焦 fan-out cap 本身
    const recipe: Recipe = {
      version: 1, name: 'split',
      nodes: [
        { id: 'in', kind: 'input', params: {} },
        { id: 'sp', kind: 'tool', toolKey: 'document.split', params: {} },
        { id: 'sp2', kind: 'tool', toolKey: 'document.split', params: {} },
      ],
      edges: [{ from: 'in', to: 'sp' }, { from: 'sp', to: 'sp2' }],
    }
    const r = new PipelineRunner(recipe, REG, h.deps, { inputFileIds: ['d1'] })
    void r.start()
    await flush()
    const outs = Array.from({ length: 40 }, (_, i) => ({ file_id: `p${i}` }))
    h.complete('t1', { output_files: outs })
    await flush()
    // 40 個產出 → 下游 cap 32
    expect(h.submitted.length).toBe(1 + 32)
    expect(r.snapshot().truncatedNodes).toContain('sp2')
  })

  it('respects in-flight cap and drains as tasks finish (polling-stall proof shape)', async () => {
    const h = makeDeps(2)
    const r = new PipelineRunner(chainRecipe(), REG, h.deps, {
      inputFileIds: ['f1', 'f2', 'f3', 'f4'],
    })
    void r.start()
    await flush()
    expect(h.submitted).toHaveLength(2)     // cap=2
    h.complete('t1', { output_file_id: 'g1' })
    await flush()
    expect(h.submitted.length).toBeGreaterThanOrEqual(3)
  })

  it('source-rooted graph submits the source task first (no file_id)', async () => {
    const h = makeDeps()
    const recipe: Recipe = {
      version: 1, name: 'dl',
      nodes: [
        { id: 's', kind: 'source', toolKey: 'video.download', params: { url: 'https://x' } },
        { id: 'tc', kind: 'tool', toolKey: 'video.transcode', params: { output_format: 'gif' } },
      ],
      edges: [{ from: 's', to: 'tc' }],
    }
    const r = new PipelineRunner(recipe, REG, h.deps, {})
    const doneP = r.start()
    await flush()
    expect(h.submitted[0].apiPath).toBe('/video/download')
    expect(h.submitted[0].params.file_id).toBeUndefined()
    expect(h.submitted[0].params.url).toBe('https://x')
    expect(h.submitted[0].params.suppress_results).toBe(true)   // 有下游

    h.complete('t1', { output_file_id: 'v1' })
    await flush()
    expect(h.submitted[1].params.file_id).toBe('v1')
    h.complete('t2', { output_file_id: 'g1' })
    await doneP
    expect(r.snapshot().status).toBe('completed')
  })

  it('keepOutput overrides suppression on intermediate nodes', async () => {
    const h = makeDeps()
    const recipe = chainRecipe()
    recipe.nodes[1].keepOutput = true
    const r = new PipelineRunner(recipe, REG, h.deps, { inputFileIds: ['f1'] })
    void r.start()
    await flush()
    expect(h.submitted[0].params.suppress_results).toBe(false)
  })

  it('cancel stops spawning and cancels in-flight tasks', async () => {
    const h = makeDeps()
    const r = new PipelineRunner(chainRecipe(), REG, h.deps, { inputFileIds: ['f1'] })
    const doneP = r.start()
    await flush()
    await r.cancel()
    expect(h.cancelled).toContain('t1')
    h.complete('t1', { output_file_id: 'g1' })   // 已提交者完成也不再展開下游
    await flush()
    expect(h.submitted).toHaveLength(1)
    await doneP
    expect(r.snapshot().status).toBe('cancelled')
  })

  it('root file ext not in downstream inputExts is skipped (refinement)', async () => {
    const h = makeDeps()
    const recipe: Recipe = {
      version: 1, name: 'split',
      nodes: [
        { id: 'in', kind: 'input', params: {} },
        { id: 'sp', kind: 'tool', toolKey: 'document.split', params: {} },
      ],
      edges: [{ from: 'in', to: 'sp' }],
    }
    // 本測試用局部 registry 副本,避免突變共用 REG 影響後續測試
    const localReg = { ...REG, 'document.split': { ...REG['document.split'], inputExts: ['pdf'] } }
    const r = new PipelineRunner(recipe, localReg, h.deps, {
      inputFileIds: ['d1', 'd2'],
      inputFileNames: { d1: 'a.srt', d2: 'b.pdf' },
    })
    void r.start()
    await flush()
    expect(h.submitted).toHaveLength(1)              // 只有 pdf 進
    expect(h.submitted[0].params.file_id).toBe('d2')
    expect(r.snapshot().executions.some(e => e.status === 'skipped')).toBe(true)
  })

  it('input files not matching downstream inputKinds are filtered at run start', async () => {
    const h = makeDeps()
    const r = new PipelineRunner(chainRecipe(), REG, h.deps, {
      inputFileIds: ['f1'],
      inputFileKinds: { f1: 'audio' },    // 根檔案是 audio,下游 transcode 只吃 video
    })
    const doneP = r.start()
    await flush()
    expect(h.submitted).toHaveLength(0)
    await doneP
    expect(r.snapshot().executions.every(e => e.status === 'skipped')).toBe(true)
  })
})
