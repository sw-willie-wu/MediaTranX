/**
 * Pipeline 執行引擎核心（spec B2）——純 TS、deps 注入,headless 可測。
 * 事件驅動:execution 完成 → 萃取 output file_id → 對每個子節點 × 每個產出
 * 展開下游 execution（cap MAX_FANOUT_PER_NODE）。單檔失敗只斷自己的下游。
 *
 * 注意:實際接線層（W2 composable）必須以 taskStore.submitTask（或提交後
 * startPolling）實作 deps.submit——裸 POST 會踩 tasks store 在 activeTasks
 * 歸零同 tick stopPolling 的行為,直鏈中段的新任務永遠不被輪詢,run 卡死。
 */
import type { Recipe, RecipeNode, ToolSpec } from './types'
import type { MediaKindT } from '@/utils/mediaKind'

export const MAX_FANOUT_PER_NODE = 32

export interface EngineDeps {
  /** 提交任務,回 taskId。實作必須保證該 task 之後會被追蹤到 terminal。 */
  submit(apiPath: string, params: Record<string, unknown>): Promise<string>
  /** taskId 進 terminal（completed/failed/cancelled）時回呼一次。 */
  onTaskTerminal(taskId: string, cb: (t: { status: string; result: unknown }) => void): void
  cancel(taskId: string): Promise<void>
  maxInFlight(): number
}

export interface Execution {
  id: string
  nodeId: string
  toolKey: string
  /** 上游餵入的檔案（source execution 無） */
  inputFileId?: string
  taskId?: string
  status: 'queued' | 'submitted' | 'completed' | 'failed' | 'skipped' | 'cancelled'
  outputFileIds: string[]
}

export interface RunSnapshot {
  status: 'idle' | 'running' | 'completed' | 'completed_with_errors' | 'cancelled'
  executions: Execution[]
  /** 多產出 fan-out 被 cap 截斷的節點（no silent caps） */
  truncatedNodes: string[]
}

export interface RunnerOptions {
  inputFileIds?: string[]
  /** 根檔案的媒體類別（已知時提供;未提供不擋、交後端） */
  inputFileKinds?: Record<string, MediaKindT>
  /** 根檔案的檔名（inputExts refinement 用;未提供不擋、交後端） */
  inputFileNames?: Record<string, string>
}

/** 鏡像後端 _collect_output_ids 慣例 */
export function collectOutputIds(result: unknown): string[] {
  const seen: string[] = []
  if (result === null || typeof result !== 'object') return seen
  const r = result as Record<string, unknown>
  for (const [key, value] of Object.entries(r)) {
    if (typeof value === 'string' && key.endsWith('_file_id') && !seen.includes(value)) {
      seen.push(value)
    } else if (key === 'output_files' && Array.isArray(value)) {
      for (const item of value) {
        const fid = (item as { file_id?: unknown })?.file_id
        if (typeof fid === 'string' && !seen.includes(fid)) seen.push(fid)
      }
    }
  }
  return seen
}

export class PipelineRunner {
  private readonly nodeById = new Map<string, RecipeNode>()
  private readonly children = new Map<string, string[]>()
  private readonly executions: Execution[] = []
  private readonly pendingQueue: Execution[] = []
  private readonly truncated = new Set<string>()
  private inFlight = 0
  private seq = 0
  private cancelled = false
  private hadFailure = false
  private started = false
  private donePromise!: Promise<void>
  private resolveDone!: () => void

  constructor(
    private readonly recipe: Recipe,
    private readonly registry: Record<string, ToolSpec>,
    private readonly deps: EngineDeps,
    private readonly options: RunnerOptions,
  ) {
    for (const n of recipe.nodes) this.nodeById.set(n.id, n)
    for (const e of recipe.edges) {
      const arr = this.children.get(e.from) ?? []
      arr.push(e.to)
      this.children.set(e.from, arr)
    }
  }

  /** 開跑;回傳的 promise 在 run 進 terminal 時 resolve。 */
  start(): Promise<void> {
    if (this.started) return this.donePromise
    this.started = true
    this.donePromise = new Promise((r) => { this.resolveDone = r })

    const root = this.recipe.nodes.find(n => n.kind === 'input' || n.kind === 'source')
    if (!root) {
      this.resolveDone()
      return this.donePromise
    }

    if (root.kind === 'source') {
      this.enqueue(root.id, undefined)
    } else {
      const files = this.options.inputFileIds ?? []
      for (const fid of files) {
        for (const childId of this.children.get(root.id) ?? []) {
          this.spawnChild(childId, fid)
        }
      }
    }
    this.pump()
    this.checkDone()
    return this.donePromise
  }

  async cancel(): Promise<void> {
    this.cancelled = true
    // 佇列中未提交的全標 cancelled
    for (const ex of this.pendingQueue.splice(0)) {
      ex.status = 'cancelled'
    }
    // 已提交的走 task cancel API
    const inflightIds = this.executions
      .filter(e => e.status === 'submitted' && e.taskId)
      .map(e => e.taskId!)
    await Promise.all(inflightIds.map(id => this.deps.cancel(id)))
    this.checkDone()
  }

  snapshot(): RunSnapshot {
    let status: RunSnapshot['status']
    if (!this.started) status = 'idle'
    else if (this.cancelled) status = 'cancelled'
    else if (this.isSettled()) status = this.hadFailure ? 'completed_with_errors' : 'completed'
    else status = 'running'
    return {
      status,
      executions: [...this.executions],
      truncatedNodes: [...this.truncated],
    }
  }

  // ── internals ─────────────────────────────────────────────────────

  private spawnChild(nodeId: string, inputFileId: string): void {
    const node = this.nodeById.get(nodeId)
    if (!node || node.kind !== 'tool' || !node.toolKey) return
    const spec = this.registry[node.toolKey]
    if (!spec) return
    // 根檔案類別已知時前置過濾（中間節點類別由 registry outputKind 靜態保證）
    const known = this.options.inputFileKinds?.[inputFileId]
    if (known && !spec.inputKinds.includes(known)) {
      this.executions.push({
        id: `x${++this.seq}`, nodeId, toolKey: node.toolKey,
        inputFileId, status: 'skipped', outputFileIds: [],
      })
      this.skipDescendants(nodeId, `input kind ${known} not accepted`)
      return
    }
    // inputExts refinement（宣告了就以它為準;檔名未知交後端把關）
    const name = this.options.inputFileNames?.[inputFileId]
    if (name && spec.inputExts && spec.inputExts.length > 0) {
      const ext = name.includes('.') ? name.slice(name.lastIndexOf('.') + 1).toLowerCase() : ''
      if (!spec.inputExts.includes(ext)) {
        this.executions.push({
          id: `x${++this.seq}`, nodeId, toolKey: node.toolKey,
          inputFileId, status: 'skipped', outputFileIds: [],
        })
        this.skipDescendants(nodeId, `ext .${ext} not in [${spec.inputExts.join(',')}]`)
        return
      }
    }
    this.enqueue(nodeId, inputFileId)
  }

  private enqueue(nodeId: string, inputFileId: string | undefined): void {
    const node = this.nodeById.get(nodeId)!
    const ex: Execution = {
      id: `x${++this.seq}`,
      nodeId,
      toolKey: node.toolKey!,
      inputFileId,
      status: 'queued',
      outputFileIds: [],
    }
    this.executions.push(ex)
    this.pendingQueue.push(ex)
  }

  private pump(): void {
    while (!this.cancelled && this.inFlight < this.deps.maxInFlight() && this.pendingQueue.length > 0) {
      const ex = this.pendingQueue.shift()!
      void this.submitExecution(ex)
    }
  }

  private async submitExecution(ex: Execution): Promise<void> {
    const node = this.nodeById.get(ex.nodeId)!
    const spec = this.registry[node.toolKey!]!
    const isLeaf = (this.children.get(ex.nodeId) ?? []).length === 0
    const suppress = !(isLeaf || node.keepOutput === true)

    const params: Record<string, unknown> = { ...node.params, suppress_results: suppress }
    if (ex.inputFileId !== undefined) params.file_id = ex.inputFileId

    this.inFlight++
    ex.status = 'submitted'
    try {
      const taskId = await this.deps.submit(spec.apiPath, params)
      ex.taskId = taskId
      this.deps.onTaskTerminal(taskId, (t) => this.onTerminal(ex, t))
    } catch {
      this.inFlight--
      ex.status = 'failed'
      this.hadFailure = true
      this.skipDescendants(ex.nodeId, 'submit failed')
      this.pump()
      this.checkDone()
    }
  }

  private onTerminal(ex: Execution, t: { status: string; result: unknown }): void {
    if (ex.status !== 'submitted') return
    this.inFlight--
    if (t.status === 'completed') {
      ex.status = 'completed'
      ex.outputFileIds = collectOutputIds(t.result)
      if (!this.cancelled) {
        const childIds = this.children.get(ex.nodeId) ?? []
        for (const childId of childIds) {
          const capped = ex.outputFileIds.slice(0, MAX_FANOUT_PER_NODE)
          if (ex.outputFileIds.length > MAX_FANOUT_PER_NODE) this.truncated.add(childId)
          for (const fid of capped) this.spawnChild(childId, fid)
        }
      }
    } else if (t.status === 'cancelled') {
      ex.status = 'cancelled'
    } else {
      ex.status = 'failed'
      this.hadFailure = true
      this.skipDescendants(ex.nodeId, 'upstream failed')
    }
    this.pump()
    this.checkDone()
  }

  /** 失敗/類別不符時把該分支「將會發生」的下游標為 skipped（記帳用）。 */
  private skipDescendants(nodeId: string, _reason: string): void {
    for (const childId of this.children.get(nodeId) ?? []) {
      const node = this.nodeById.get(childId)
      if (!node) continue
      this.executions.push({
        id: `x${++this.seq}`, nodeId: childId, toolKey: node.toolKey ?? '',
        status: 'skipped', outputFileIds: [],
      })
      this.skipDescendants(childId, _reason)
    }
  }

  private isSettled(): boolean {
    return this.inFlight === 0 && this.pendingQueue.length === 0
  }

  private checkDone(): void {
    if (this.started && this.isSettled()) {
      this.resolveDone()
    }
  }
}
