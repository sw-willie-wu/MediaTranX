/**
 * Pipeline 編輯器 store — 多文件（分頁）：docs[] + activeDocId，對外介面
 * （recipe/selectedNodeId/…）代理到 active doc 的 writable computed。
 * 引擎接線:deps.submit 走 fetch + taskStore.addTask(**必須**經 store 讓輪詢
 * re-arm——裸 POST 會踩 activeTasks 歸零同 tick stopPolling,直鏈 run 卡死)。
 * run 歸屬:runner 由 startRun closure 捕獲所屬 doc——跑中切分頁,進度/終局
 * snapshot 仍寫回原 doc;全域一次一 run（runningDocId 兼同步重入鎖）。
 */
import { defineStore } from 'pinia'
import { computed, readonly, ref, watch } from 'vue'
import i18n from '@/i18n'
import { getApiBase } from '@/composables/useApi'
import { useTaskStore } from '@/stores/tasks'
import { useComputeSettingsStore } from '@/stores/computeSettings'
import { TOOL_REGISTRY } from '@/pipeline/registry'
import { normalizeParams, validateRecipe } from '@/pipeline/recipe'
import { PipelineRunner, type EngineDeps, type RunSnapshot } from '@/pipeline/runner'
import type { Recipe, ValidationIssue } from '@/pipeline/types'
import type { MediaKindT } from '@/utils/mediaKind'
import { detectMediaKind } from '@/utils/mediaKind'
import { createLogger } from '@/utils/logger'
import { useModelStore } from '@/stores/models'
import { METAS } from '@/components/params'
import { isModelInstalled } from '@/components/params/modelGuardUtils'

const log = createLogger('PipelineStore')

export interface RunInputFile {
  fileId: string
  filename: string
}

export const MAX_DOCS = 8

/** 一個畫布分頁＝一份獨立文件（spec §5.1） */
export interface PipelineDoc {
  id: string
  name: string
  recipe: Recipe
  selectedNodeId: string | null
  inputFiles: RunInputFile[]
  runSnapshot: RunSnapshot | null
  currentRunId: string | null
  currentRecipeId: string | null
  /** per-doc！模組級單例會讓 A 頁的 model_missing 洩漏到 B 頁 issue bar */
  modelIssues: ValidationIssue[]
  nodeSeq: number
}

function emptyRecipe(): Recipe {
  return {
    version: 1,
    name: '',
    nodes: [{ id: 'input-1', kind: 'input', params: {}, position: { x: 60, y: 200 } }],
    edges: [],
  }
}

let docSeq = 0
function createDoc(): PipelineDoc {
  return {
    id: `doc-${++docSeq}-${Date.now() % 100000}`,
    name: '',
    recipe: emptyRecipe(),
    selectedNodeId: null,
    inputFiles: [],
    runSnapshot: null,
    currentRunId: null,
    currentRecipeId: null,
    modelIssues: [],
    nodeSeq: 1,
  }
}

export const usePipelineStore = defineStore('pipeline', () => {
  const taskStore = useTaskStore()
  const computeStore = useComputeSettingsStore()
  const modelStore = useModelStore()

  // ── 多文件核心 ─────────────────────────────────────────────────────
  const docs = ref<PipelineDoc[]>([createDoc()])
  const activeDocId = ref<string>(docs.value[0].id)
  const activeDoc = computed(() => docs.value.find(d => d.id === activeDocId.value) ?? docs.value[0])
  /** 全域一次一 run＋同步重入鎖（startRun 開頭、任何 await 前設值） */
  const runningDocId = ref<string | null>(null)

  // ── 代理層:對外介面與單文件時代一致，讀寫 active doc ────────────────
  const recipe = computed({ get: () => activeDoc.value.recipe, set: (v: Recipe) => { activeDoc.value.recipe = v } })
  const selectedNodeId = computed({ get: () => activeDoc.value.selectedNodeId, set: (v: string | null) => { activeDoc.value.selectedNodeId = v } })
  const inputFiles = computed({ get: () => activeDoc.value.inputFiles, set: (v: RunInputFile[]) => { activeDoc.value.inputFiles = v } })
  const runSnapshot = computed({ get: () => activeDoc.value.runSnapshot, set: (v: RunSnapshot | null) => { activeDoc.value.runSnapshot = v } })
  const currentRunId = computed({ get: () => activeDoc.value.currentRunId, set: (v: string | null) => { activeDoc.value.currentRunId = v } })
  const currentRecipeId = computed({ get: () => activeDoc.value.currentRecipeId, set: (v: string | null) => { activeDoc.value.currentRecipeId = v } })

  const running = computed(() => runningDocId.value === activeDocId.value)
  let runner: PipelineRunner | null = null
  let snapTimer: ReturnType<typeof setInterval> | null = null

  // 圖結構驗證（連線/參數/度數……）；純函式、隨 recipe 變動即時重算。
  const structuralIssues = computed(() => validateRecipe(recipe.value, TOOL_REGISTRY))
  const issues = computed(() => [...structuralIssues.value, ...activeDoc.value.modelIssues])
  const errors = computed(() => issues.value.filter(i => i.severity === 'error'))
  // canRun 刻意只看結構性 errors（不含 modelIssues）：模型缺失不該永久鎖死執行鈕——
  // 使用者裝好模型後要能直接再按一次執行重新驗證,而非卡在「按鈕本身被 disable」。
  const canRun = computed(() => {
    if (runningDocId.value !== null) return false   // 全域 gate:任何分頁在跑一律 false
    const structuralErrors = structuralIssues.value.filter(i => i.severity === 'error')
    if (structuralErrors.length > 0) return false
    const root = recipe.value.nodes.find(n => n.kind === 'input' || n.kind === 'source')
    if (!root) return false
    if (root.kind === 'input') return inputFiles.value.length > 0
    return true
  })

  const selectedNode = computed(() =>
    recipe.value.nodes.find(n => n.id === selectedNodeId.value) ?? null)

  // ── 分頁投影/查詢 ──────────────────────────────────────────────────
  const tabs = computed(() => docs.value.map(d => ({
    id: d.id, name: d.name, running: runningDocId.value === d.id, active: d.id === activeDocId.value,
  })))

  function findRunDoc(runId: string): PipelineDoc | null {
    return docs.value.find(d => d.currentRunId === runId) ?? null
  }

  /** 空白＝只有預設 input 根、無 tool/source 節點、無 edge（emptyRecipe 恆帶 input 根） */
  function isBlankDoc(doc?: PipelineDoc): boolean {
    const d = doc ?? activeDoc.value
    return d.recipe.edges.length === 0 && d.recipe.nodes.every(n => n.kind === 'input')
  }
  function isBlankDocId(id: string): boolean {
    const d = docs.value.find(x => x.id === id)
    return d ? isBlankDoc(d) : false
  }

  /** 開新空白分頁並 focus（spec §3/§5.3）；滿 MAX_DOCS 回 null 由呼叫端 toast */
  function newDoc(): string | null {
    if (docs.value.length >= MAX_DOCS) return null
    const d = createDoc()
    docs.value.push(d)
    activeDocId.value = d.id
    return d.id
  }

  // ── 圖編輯 ─────────────────────────────────────────────────────────
  function addToolNode(toolKey: string, position: { x: number; y: number }): string {
    const spec = TOOL_REGISTRY[toolKey]
    if (!spec) return ''
    const id = `n${++activeDoc.value.nodeSeq}-${Date.now() % 100000}`
    const params: Record<string, unknown> = {}
    for (const f of spec.paramSchema) {
      if (f.default !== undefined) params[f.name] = f.default
    }
    recipe.value.nodes.push({
      id, kind: spec.kind === 'source' ? 'source' : 'tool',
      toolKey, params, position,
    })
    // source 取代 input 根（恰一根:放 source 就移除空 input 根）
    if (spec.kind === 'source') {
      const inputRoot = recipe.value.nodes.find(n => n.kind === 'input')
      if (inputRoot && !recipe.value.edges.some(e => e.from === inputRoot.id)) {
        recipe.value.nodes = recipe.value.nodes.filter(n => n.id !== inputRoot.id)
      }
    }
    selectedNodeId.value = id
    return id
  }

  function removeNode(id: string) {
    recipe.value.nodes = recipe.value.nodes.filter(n => n.id !== id)
    recipe.value.edges = recipe.value.edges.filter(e => e.from !== id && e.to !== id)
    if (selectedNodeId.value === id) selectedNodeId.value = null
    // 根全沒了 → 補回 input 根
    if (!recipe.value.nodes.some(n => n.kind === 'input' || n.kind === 'source')) {
      recipe.value.nodes.push({ id: 'input-1', kind: 'input', params: {}, position: { x: 60, y: 200 } })
    }
  }

  /** 連線;成功回 null、失敗回退並回傳具體原因（給 toast） */
  function connect(from: string, to: string): string | null {
    if (recipe.value.edges.some(e => e.from === from && e.to === to)) return null
    recipe.value.edges.push({ from, to })
    const bad = validateRecipe(recipe.value, TOOL_REGISTRY)
      .find(i => i.severity === 'error' && (i.edge?.from === from && i.edge?.to === to))
    if (bad) {
      recipe.value.edges = recipe.value.edges.filter(e => !(e.from === from && e.to === to))
      return bad.message
    }
    return null
  }

  function disconnect(from: string, to: string) {
    recipe.value.edges = recipe.value.edges.filter(e => !(e.from === from && e.to === to))
  }

  function updateNodeParams(id: string, params: Record<string, unknown>) {
    const n = recipe.value.nodes.find(x => x.id === id)
    if (n) n.params = { ...params }
  }

  function setKeepOutput(id: string, keep: boolean) {
    const n = recipe.value.nodes.find(x => x.id === id)
    if (n) n.keepOutput = keep
  }

  function moveNode(id: string, position: { x: number; y: number }) {
    const n = recipe.value.nodes.find(x => x.id === id)
    if (n) n.position = position
  }

  /** reset active doc（分頁化後語意＝清當前分頁內容，不動其他分頁） */
  function reset() {
    const d = activeDoc.value
    d.recipe = emptyRecipe()
    d.selectedNodeId = null
    d.inputFiles = []
    d.runSnapshot = null
    d.modelIssues = []
  }

  // ── 引擎接線 ───────────────────────────────────────────────────────
  const terminalCallbacks = new Map<string, (t: { status: string; result: unknown }) => void>()

  watch(
    () => Array.from(taskStore.tasks.values()).map(t => `${t.taskId}:${t.status}`).join('|'),
    () => {
      for (const t of taskStore.tasks.values()) {
        if (['completed', 'failed', 'cancelled'].includes(t.status)) {
          const cb = terminalCallbacks.get(t.taskId)
          if (cb) {
            terminalCallbacks.delete(t.taskId)
            cb({ status: t.status, result: t.result })
          }
        }
      }
    },
  )

  function makeDeps(): EngineDeps {
    return {
      async submit(apiPath, params) {
        const spec = Object.values(TOOL_REGISTRY).find(s => s.apiPath === apiPath)
        const resp = await fetch(`${getApiBase()}${apiPath}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(params),
        })
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}))
          throw new Error(err.detail || `HTTP ${resp.status}`)
        }
        const { task_id: taskId } = await resp.json()
        // 經 taskStore 註冊 → 輪詢 re-arm（引擎生死攸關,見檔頭）
        taskStore.addTask({
          taskId,
          taskType: spec?.toolKey ?? apiPath,
          status: 'pending',
          progress: 0,
          message: '',
          result: null,
          error: null,
          createdAt: new Date(),
          updatedAt: new Date(),
          // i18n 解析而非 raw toolKey — in-session 任務清單顯示與 reload
          // (tasks.types)同字樣
          label: spec ? i18n.global.t(spec.labelKey) : apiPath,
        })
        return taskId
      },
      onTaskTerminal(taskId, cb) {
        // 已 terminal 的直接回呼（watch 只看變化）
        const t = taskStore.tasks.get(taskId)
        if (t && ['completed', 'failed', 'cancelled'].includes(t.status)) {
          cb({ status: t.status, result: t.result })
          return
        }
        terminalCallbacks.set(taskId, cb)
      },
      async cancel(taskId) {
        await taskStore.cancelTask(taskId)
      },
      maxInFlight: () => computeStore.settings.max_concurrent_tasks ?? 4,
    }
  }

  /**
   * startRun 前逐 tool/source 節點驗模型（Task 1.6）。吃捕獲的 doc——本函式跨
   * await（ensureLoaded），期間使用者可能切分頁,讀寫代理會驗到/寫進別頁。
   */
  async function checkModelsReady(doc: PipelineDoc): Promise<boolean> {
    await modelStore.ensureLoaded()
    const missing: ValidationIssue[] = []
    for (const node of doc.recipe.nodes) {
      if (node.kind !== 'tool' && node.kind !== 'source') continue
      if (!node.toolKey) continue
      const meta = METAS[node.toolKey]
      // 複數優先於單數（與 ToolParamHost.preflight() 同構，見該檔 modelRequirements 註解——
      // 兩者互斥，若都設以複數為準；單數存在時包成單元素陣列走同一迴圈）。
      const plural = meta?.modelRequirements?.(node.params)
      const singular = meta?.modelRequirement?.(node.params)
      const reqs = plural ?? (singular ? [singular] : [])
      for (const req of reqs) {
        if (isModelInstalled(modelStore.models, req)) continue
        const label =
          [req.family, req.size, req.quantization].filter(Boolean).join(' ') ||
          req.variant ||
          (req.categories && req.categories.length > 0 ? req.categories.join('/') : '')
        missing.push({
          severity: 'error',
          nodeId: node.id,
          code: 'model_missing',
          message: `node ${node.id} (${node.toolKey}) requires model ${label} (not installed)`,
        })
      }
    }
    doc.modelIssues = missing
    return missing.length === 0
  }

  async function startRun(): Promise<void> {
    if (runningDocId.value !== null || !canRun.value) return
    const doc = activeDoc.value            // 捕獲——此後一律 doc.*，不碰 active 代理
    runningDocId.value = doc.id            // 同步重入鎖（任何 await 之前）
    let started = false
    if (snapTimer) { clearInterval(snapTimer); snapTimer = null }
    try {
      if (!(await checkModelsReady(doc))) return   // finally 會還鎖
      const kinds: Record<string, MediaKindT> = {}
      const names: Record<string, string> = {}
      for (const f of doc.inputFiles) {
        const k = detectMediaKind(f.filename)
        if (k) kinds[f.fileId] = k
        names[f.fileId] = f.filename
      }
      runner = new PipelineRunner(
        JSON.parse(JSON.stringify(doc.recipe)) as Recipe,   // snapshot
        TOOL_REGISTRY,
        makeDeps(),
        {
          inputFileIds: doc.inputFiles.map(f => f.fileId),
          inputFileKinds: kinds,
          inputFileNames: names,
        },
      )
      started = true
      doc.runSnapshot = runner.snapshot()
      snapTimer = setInterval(() => { doc.runSnapshot = runner?.snapshot() ?? null }, 400)
      log.info('run start', { doc: doc.id, nodes: doc.recipe.nodes.length, files: doc.inputFiles.length })
      await runner.start()
    } finally {
      if (snapTimer) { clearInterval(snapTimer); snapTimer = null }
      // 只在真正起跑後寫終局 snapshot——未起跑（model-missing early return）時
      // runner 還指著上一輪 run，無條件寫會把舊快照灌進本輪捕獲的 doc
      if (started) {
        doc.runSnapshot = runner?.snapshot() ?? null
        log.info('run done', { doc: doc.id, status: doc.runSnapshot?.status })
      }
      runningDocId.value = null            // 一律還鎖（early return/例外/跑完）
    }
  }

  async function cancelRun(): Promise<void> {
    const doc = docs.value.find(d => d.id === runningDocId.value)
    await runner?.cancel()
    if (doc) doc.runSnapshot = runner?.snapshot() ?? null
  }

  // ── 持久化（W3）────────────────────────────────────────────────────
  interface SavedRecipeMeta { id: string; name: string; updated_at: string }
  const savedRecipes = ref<SavedRecipeMeta[]>([])

  async function loadRecipeList(): Promise<void> {
    try {
      const res = await fetch(`${getApiBase()}/pipeline/recipes`)
      if (!res.ok) return
      const data = await res.json() as Array<SavedRecipeMeta>
      savedRecipes.value = data.map(({ id, name, updated_at }) => ({ id, name, updated_at }))
    } catch (e) {
      log.warn('loadRecipeList failed', e)
    }
  }

  async function saveCurrent(name: string): Promise<boolean> {
    const body = JSON.stringify({ name, graph: JSON.stringify(recipe.value) })
    const url = currentRecipeId.value
      ? `${getApiBase()}/pipeline/recipes/${currentRecipeId.value}`
      : `${getApiBase()}/pipeline/recipes`
    try {
      const res = await fetch(url, {
        method: currentRecipeId.value ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      })
      if (!res.ok) return false
      const data = await res.json()
      currentRecipeId.value = data.id
      recipe.value.name = name
      activeDoc.value.name = name          // doc.name 唯一權威名（spec §3）
      await loadRecipeList()
      return true
    } catch (e) {
      log.error('saveCurrent failed', e)
      return false
    }
  }

  /** 載入已存 recipe;revalidate-on-load:未知參數剝除、缺項補 default、缺座標補位。 */
  async function openRecipe(id: string): Promise<boolean> {
    try {
      const res = await fetch(`${getApiBase()}/pipeline/recipes/${id}`)
      if (!res.ok) return false
      const data = await res.json()
      const parsed = JSON.parse(data.graph) as Recipe
      let i = 0
      for (const n of parsed.nodes) {
        if (!n.position) n.position = { x: 80 + (i++) * 190, y: 200 }
        if (n.kind !== 'input' && n.toolKey) {
          const spec = TOOL_REGISTRY[n.toolKey]
          if (spec) n.params = normalizeParams(n.params ?? {}, spec).params
        }
      }
      const doc = activeDoc.value
      doc.recipe = parsed
      doc.name = data.name ?? parsed.name ?? ''
      doc.currentRecipeId = id
      doc.selectedNodeId = null
      doc.runSnapshot = null
      doc.modelIssues = []
      // nodeSeq 取既有 id 數字前綴最大值（刪除過節點時 length 會低估）
      doc.nodeSeq = parsed.nodes.reduce((mx, nd) => {
        const m = /^n(\d+)-/.exec(nd.id)
        return m ? Math.max(mx, Number(m[1])) : mx
      }, 1)
      return true
    } catch (e) {
      log.error('openRecipe failed', e)
      return false
    }
  }

  async function deleteRecipe(id: string): Promise<void> {
    try {
      await fetch(`${getApiBase()}/pipeline/recipes/${id}`, { method: 'DELETE' })
    } catch (e) {
      log.warn('deleteRecipe failed', e)
    }
    // 刪到已開啟的 recipe:刻意保留畫布內容（不清使用者工作）,
    // 只解除關聯——下次存檔會變成新 recipe（POST）。掃全部分頁。
    for (const d of docs.value) {
      if (d.currentRecipeId === id) d.currentRecipeId = null
    }
    await loadRecipeList()
  }

  function newRecipe(): void {
    reset()
    currentRecipeId.value = null
  }

  return {
    recipe, selectedNodeId, selectedNode, inputFiles, issues, errors, canRun,
    runSnapshot, running,
    addToolNode, removeNode, connect, disconnect, updateNodeParams,
    setKeepOutput, moveNode, reset, startRun, cancelRun,
    savedRecipes, currentRecipeId, currentRunId, loadRecipeList, saveCurrent,
    openRecipe, deleteRecipe, newRecipe,
    // 多文件（分頁）
    activeDocId, runningDocId: readonly(runningDocId), tabs,
    newDoc, findRunDoc, isBlankDoc, isBlankDocId,
  }
})
