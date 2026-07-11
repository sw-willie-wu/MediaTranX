/**
 * Pipeline 編輯器 store — 當前 recipe 圖、選取節點、驗證結果、run 狀態。
 * 引擎接線:deps.submit 走 fetch + taskStore.addTask(**必須**經 store 讓輪詢
 * re-arm——裸 POST 會踩 activeTasks 歸零同 tick stopPolling,直鏈 run 卡死)。
 */
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import i18n from '@/i18n'
import { getApiBase } from '@/composables/useApi'
import { useTaskStore } from '@/stores/tasks'
import { useComputeSettingsStore } from '@/stores/computeSettings'
import { TOOL_REGISTRY } from '@/pipeline/registry'
import { normalizeParams, validateRecipe } from '@/pipeline/recipe'
import { PipelineRunner, type EngineDeps, type RunSnapshot } from '@/pipeline/runner'
import type { Recipe, RecipeNode } from '@/pipeline/types'
import type { MediaKindT } from '@/utils/mediaKind'
import { detectMediaKind } from '@/utils/mediaKind'
import { createLogger } from '@/utils/logger'

const log = createLogger('PipelineStore')

export interface RunInputFile {
  fileId: string
  filename: string
}

function emptyRecipe(): Recipe {
  return {
    version: 1,
    name: '',
    nodes: [{ id: 'input-1', kind: 'input', params: {}, position: { x: 60, y: 200 } }],
    edges: [],
  }
}

export const usePipelineStore = defineStore('pipeline', () => {
  const taskStore = useTaskStore()
  const computeStore = useComputeSettingsStore()

  const recipe = ref<Recipe>(emptyRecipe())
  const selectedNodeId = ref<string | null>(null)
  const inputFiles = ref<RunInputFile[]>([])
  const runSnapshot = ref<RunSnapshot | null>(null)
  // 同步重入鎖:runSnapshot 由 400ms timer 更新,不能拿它擋 double-click
  const runActive = ref(false)
  // agent run_pipeline 的 run 識別（get_task_status run 聚合查詢用）
  const currentRunId = ref<string | null>(null)
  const running = computed(() => runActive.value || runSnapshot.value?.status === 'running')
  let runner: PipelineRunner | null = null
  let snapTimer: ReturnType<typeof setInterval> | null = null
  let nodeSeq = 1

  const issues = computed(() => validateRecipe(recipe.value, TOOL_REGISTRY))
  const errors = computed(() => issues.value.filter(i => i.severity === 'error'))
  const canRun = computed(() => {
    if (errors.value.length > 0 || running.value) return false
    const root = recipe.value.nodes.find(n => n.kind === 'input' || n.kind === 'source')
    if (!root) return false
    if (root.kind === 'input') return inputFiles.value.length > 0
    return true
  })

  const selectedNode = computed(() =>
    recipe.value.nodes.find(n => n.id === selectedNodeId.value) ?? null)

  // ── 圖編輯 ─────────────────────────────────────────────────────────
  function addToolNode(toolKey: string, position: { x: number; y: number }): string {
    const spec = TOOL_REGISTRY[toolKey]
    if (!spec) return ''
    const id = `n${++nodeSeq}-${Date.now() % 100000}`
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

  function reset() {
    recipe.value = emptyRecipe()
    selectedNodeId.value = null
    inputFiles.value = []
    runSnapshot.value = null
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

  async function startRun(): Promise<void> {
    if (runActive.value || !canRun.value) return
    runActive.value = true
    if (snapTimer) { clearInterval(snapTimer); snapTimer = null }
    const kinds: Record<string, MediaKindT> = {}
    const names: Record<string, string> = {}
    for (const f of inputFiles.value) {
      const k = detectMediaKind(f.filename)
      if (k) kinds[f.fileId] = k
      names[f.fileId] = f.filename
    }
    runner = new PipelineRunner(
      JSON.parse(JSON.stringify(recipe.value)) as Recipe,   // snapshot
      TOOL_REGISTRY,
      makeDeps(),
      {
        inputFileIds: inputFiles.value.map(f => f.fileId),
        inputFileKinds: kinds,
        inputFileNames: names,
      },
    )
    runSnapshot.value = runner.snapshot()
    snapTimer = setInterval(() => { runSnapshot.value = runner?.snapshot() ?? null }, 400)
    log.info('run start', { nodes: recipe.value.nodes.length, files: inputFiles.value.length })
    try {
      await runner.start()
    } finally {
      if (snapTimer) { clearInterval(snapTimer); snapTimer = null }
      runSnapshot.value = runner?.snapshot() ?? null
      runActive.value = false
      log.info('run done', { status: runSnapshot.value?.status })
    }
  }

  async function cancelRun(): Promise<void> {
    await runner?.cancel()
    runSnapshot.value = runner?.snapshot() ?? null
  }

  // ── 持久化（W3）────────────────────────────────────────────────────
  interface SavedRecipeMeta { id: string; name: string; updated_at: string }
  const savedRecipes = ref<SavedRecipeMeta[]>([])
  const currentRecipeId = ref<string | null>(null)

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
      recipe.value = parsed
      recipe.value.name = data.name
      currentRecipeId.value = id
      selectedNodeId.value = null
      runSnapshot.value = null
      // nodeSeq 取既有 id 數字前綴最大值（刪除過節點時 length 會低估）
      nodeSeq = parsed.nodes.reduce((mx, nd) => {
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
    // 刪到當前開啟的 recipe:刻意保留畫布內容（不清使用者工作）,
    // 只解除關聯——下次存檔會變成新 recipe（POST）。
    if (currentRecipeId.value === id) currentRecipeId.value = null
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
  }
})
