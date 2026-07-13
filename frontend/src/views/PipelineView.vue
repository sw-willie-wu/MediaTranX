<script setup lang="ts">
/**
 * Pipeline 畫布（spec B3）— 左節點盤 / 中 Vue Flow / 右參數面板 / 底 run 列。
 * recipe（store）是唯一事實來源;Vue Flow nodes/edges 由 recipe 派生,
 * 拖曳/連線事件寫回 store。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Handle, Position, VueFlow, useVueFlow, type Connection, type NodeDragEvent } from '@vue-flow/core'
import AppThreePaneLayout from '@/components/common/AppThreePaneLayout.vue'
import { usePipelineStore } from '@/stores/pipeline'
import { useFilesStore } from '@/stores/files'
import { useToast } from '@/composables/useToast'
import { TOOL_REGISTRY, listToolSpecs } from '@/pipeline/registry'
import type { RecipeNode } from '@/pipeline/types'
import PipelineParamForm from '@/components/pipeline/PipelineParamForm.vue'
import AppMediaInfoBar, { type InfoItem } from '@/components/common/AppMediaInfoBar.vue'

const { t } = useI18n()
const store = usePipelineStore()
const filesStore = useFilesStore()
const toast = useToast()
const { screenToFlowCoordinate, fitView, onPaneReady, viewport } = useVueFlow()

// 底部資訊列：目前縮放百分比（viewport 響應 pan/zoom；形狀沿 ImageView 的 imageInfoItems）
const canvasInfoItems = computed<InfoItem[]>(() => [
  { icon: 'bi-zoom-in', label: `${Math.round(viewport.value.zoom * 100)}%` },
])

// fitView 在節點少時會把 zoom 拉滿填畫布（1-2 個節點時看起來巨大）——
// maxZoom:1 讓「置中」不「放大」；使用者仍可手動 zoom（受 VueFlow 預設上限）
const FIT_VIEW_OPTS = { padding: 0.25, maxZoom: 1 } as const

// 取代 fit-view-on-init（boolean prop 吃不到 maxZoom 選項）
onPaneReady(() => fitView(FIT_VIEW_OPTS))

// ── 節點盤（依域分組）─────────────────────────────────────────────
const paletteGroups = computed(() => {
  const groups: Record<string, { key: string; label: string }[]> = {}
  for (const spec of listToolSpecs()) {
    const domain = spec.toolKey.split('.')[0]
    ;(groups[domain] ??= []).push({ key: spec.toolKey, label: t(spec.labelKey) })
  }
  return groups
})

// 節點盤各類別折疊狀態（預設全收合;展開/收合選擇記 localStorage、下次沿用）
const PALETTE_OPEN_KEY = 'pipeline-palette-open'
const openSections = ref<Record<string, boolean>>((() => {
  try { return JSON.parse(localStorage.getItem(PALETTE_OPEN_KEY) || '{}') } catch { return {} }
})())
function isSectionOpen(id: string): boolean {
  return openSections.value[id] === true
}
function toggleSection(id: string) {
  openSections.value = { ...openSections.value, [id]: !openSections.value[id] }
  localStorage.setItem(PALETTE_OPEN_KEY, JSON.stringify(openSections.value))
}

// ── recipe → Vue Flow 派生 ────────────────────────────────────────
/** 中段省略保留結尾（含副檔名）：verylongname_v2.jpg → verylo…e_v2.jpg */
function truncateMiddle(name: string, max = 18): string {
  if (name.length <= max) return name
  return `${name.slice(0, max - 9)}…${name.slice(-8)}`
}

// 輸入節點的顯示文字＝檔案選取狀態（空→「選取檔案」；有→檔名，多檔加 +N）
const inputNodeLabel = computed(() => {
  const files = store.inputFiles
  if (!files.length) return t('pipeline.input_pick')
  const name = truncateMiddle(files[0].filename)
  return files.length > 1 ? `${name} +${files.length - 1}` : name
})

const flowNodes = computed(() =>
  store.recipe.nodes.map((n) => ({
    id: n.id,
    type: 'pipeline',
    position: n.position ?? { x: 100, y: 100 },
    data: {
      kind: n.kind,
      toolKey: n.toolKey,
      label: n.kind === 'input' ? inputNodeLabel.value : t(TOOL_REGISTRY[n.toolKey!]?.labelKey ?? n.toolKey!),
      // 省略後 hover 可看全名（多檔逐行列出）
      titleAttr: n.kind === 'input' && store.inputFiles.length
        ? store.inputFiles.map(f => f.filename).join('\n') : undefined,
      hasError: store.errors.some(i => i.nodeId === n.id),
      runState: nodeRunState(n.id),
      selected: store.selectedNodeId === n.id,
    },
  })),
)

// 節點執行狀態視覺：running（脈動外框）> failed（紅底）> done（綠底）；無 run 快照＝null
function nodeRunState(nodeId: string): 'running' | 'failed' | 'done' | null {
  const agg = nodeAgg(nodeId)
  if (!agg) return null
  if (agg.active) return 'running'
  if (agg.failed > 0) return 'failed'
  if (agg.total > 0 && agg.done === agg.total) return 'done'
  return null
}

const flowEdges = computed(() =>
  store.recipe.edges.map((e) => ({
    id: `${e.from}->${e.to}`,
    source: e.from,
    target: e.to,
    animated: store.running,
  })),
)

/** run 期間每節點的 execution 聚合 */
function nodeAgg(nodeId: string): { done: number; total: number; failed: number; active: boolean } | null {
  const snap = store.runSnapshot
  if (!snap) return null
  const exs = snap.executions.filter(x => x.nodeId === nodeId)
  if (exs.length === 0) return null
  return {
    done: exs.filter(x => x.status === 'completed').length,
    total: exs.length,
    failed: exs.filter(x => x.status === 'failed' || x.status === 'skipped').length,
    active: exs.some(x => x.status === 'submitted' || x.status === 'queued'),
  }
}

function onConnect(c: Connection) {
  if (!c.source || !c.target || store.running) return
  const err = store.connect(c.source, c.target)
  if (err) {
    toast.show(err || t('pipeline.connect_invalid'), { type: 'error', icon: 'bi-x-circle' })
  }
}

function onNodeDragStop(e: NodeDragEvent) {
  for (const n of e.nodes) store.moveNode(n.id, { x: n.position.x, y: n.position.y })
}

// 節點右上 X：輸入節點=清除已選檔案（節點是根、不移除）；工具/source 節點=移除節點
function onNodeRemoveClick(id: string, kind: string) {
  if (kind === 'input') store.inputFiles = []
  else store.removeNode(id)
}

function onNodeClick(e: { node: { id: string } }) {
  previewToolKey.value = null
  store.selectedNodeId = e.node.id
  // 輸入節點：點擊直接開檔案總管選檔（拖曳移動不觸發 node-click，VueFlow 已區分）
  const node = store.recipe.nodes.find(n => n.id === e.node.id)
  if (node?.kind === 'input' && !store.running && !uploading.value) fileInputRef.value?.click()
}

// ── 節點盤預覽:點工具名只在右欄看/調選項,按「+」才真正加到畫布 ──────
const previewToolKey = ref<string | null>(null)
const previewParams = ref<Record<string, unknown>>({})
const previewNode = computed<RecipeNode | null>(() => {
  const key = previewToolKey.value
  if (!key) return null
  return {
    id: '__preview__',
    kind: TOOL_REGISTRY[key]?.kind === 'source' ? 'source' : 'tool',
    toolKey: key,
    params: previewParams.value,
  }
})

function previewTool(toolKey: string) {
  if (previewToolKey.value !== toolKey) previewParams.value = {}
  previewToolKey.value = toolKey
  store.selectedNodeId = null
}

function onEdgeClick(e: { edge: { source: string; target: string } }) {
  store.disconnect(e.edge.source, e.edge.target)
}

// ── palette 拖放到畫布 ────────────────────────────────────────────
function onPaletteDragStart(ev: DragEvent, toolKey: string) {
  ev.dataTransfer?.setData('application/mtx-tool', toolKey)
}

function onCanvasDrop(ev: DragEvent) {
  const toolKey = ev.dataTransfer?.getData('application/mtx-tool')
  if (!toolKey) return
  // screenToFlowCoordinate 吃 client 座標、自帶容器偏移與 pan/zoom 換算;
  // 舊寫法 project({offsetX,offsetY}) 在 fitView 變換後落點會偏離游標
  const pos = screenToFlowCoordinate({ x: ev.clientX, y: ev.clientY })
  store.addToolNode(toolKey, pos)
}

function addByClick(toolKey: string) {
  // 依既有節點數橫向排開,加完 fitView 讓新節點一定在可視範圍
  const idx = store.recipe.nodes.length
  const id = store.addToolNode(toolKey, { x: 80 + idx * 190, y: 180 + (idx % 2) * 90 })
  if (!id) return
  // 預覽面板調過的參數帶進新節點,並直接選取讓右欄無縫接到節點表單
  if (previewToolKey.value === toolKey && Object.keys(previewParams.value).length > 0) {
    const seeded = store.recipe.nodes.find(n => n.id === id)?.params ?? {}
    store.updateNodeParams(id, { ...seeded, ...previewParams.value })
  }
  previewToolKey.value = null
  store.selectedNodeId = id
  setTimeout(() => fitView(FIT_VIEW_OPTS), 50)
}

// ── run 列:輸入檔 ─────────────────────────────────────────────────
const fileInputRef = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const rootIsInput = computed(() => store.recipe.nodes.some(n => n.kind === 'input'))

async function onFilesPicked(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files?.length) return
  uploading.value = true
  try {
    for (const f of Array.from(input.files)) {
      // Electron：preload 已攔 file input change 快取本機路徑——帶 sourceDir 走
      // /files/register 零搬運（大影片瞬間完成）；瀏覽器環境 fallback HTTP 整檔上傳
      const sourceDir = window.electron?.getFileSourceDir?.(f.name, f.size, f.lastModified) ?? undefined
      const fileId = await filesStore.uploadFile(f, sourceDir)
      store.inputFiles.push({ fileId, filename: f.name })
    }
  } catch (err) {
    toast.show(String(err), { type: 'error', icon: 'bi-x-circle' })
  } finally {
    uploading.value = false
    input.value = ''
  }
}

function removeInputFile(fileId: string) {
  store.inputFiles = store.inputFiles.filter(f => f.fileId !== fileId)
}

const runSummary = computed(() => {
  const snap = store.runSnapshot
  if (!snap) return ''
  const done = snap.executions.filter(x => x.status === 'completed').length
  return t('pipeline.run_progress', { done, total: snap.executions.length })
})

// 驗證錯誤變化時,若選取節點被刪除則清空
watch(() => store.recipe.nodes.length, () => {
  if (store.selectedNodeId && !store.recipe.nodes.some(n => n.id === store.selectedNodeId)) {
    store.selectedNodeId = null
  }
})

// ── 持久化 UI ─────────────────────────────────────────────────────
const recipeName = ref('')
const saving = ref(false)

onMounted(() => { void store.loadRecipeList() })

watch(() => store.recipe.name, (n) => { recipeName.value = n }, { immediate: true })

async function onSave() {
  const name = recipeName.value.trim() || t('pipeline.unnamed')
  saving.value = true
  const ok = await store.saveCurrent(name)
  saving.value = false
  toast.show(ok ? t('pipeline.saved') : t('toast.save_failed'),
    { type: ok ? 'success' : 'error', icon: ok ? 'bi-check-circle' : 'bi-x-circle' })
}

async function onOpen(id: string) {
  if (store.running) return
  const ok = await store.openRecipe(id)
  if (!ok) toast.show(t('pipeline.open_failed'), { type: 'error', icon: 'bi-x-circle' })
  setTimeout(() => fitView(FIT_VIEW_OPTS), 80)
}
</script>

<template>
  <AppThreePaneLayout>
    <!-- 左:節點盤（run 中鎖定；欄 chrome 由殼擁有） -->
    <template #left>
      <div class="palette" :class="{ locked: store.running }">
        <template v-for="(items, domain) in paletteGroups" :key="domain">
          <button class="palette-group palette-group-toggle" @click="toggleSection(domain)">
            {{ t(`nav.${domain}`) }}
            <i class="bi" :class="isSectionOpen(domain) ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
          </button>
          <template v-if="isSectionOpen(domain)">
            <button
              v-for="item in items"
              :key="item.key"
              class="palette-item"
              :class="{ 'is-previewing': previewToolKey === item.key }"
              draggable="true"
              @dragstart="onPaletteDragStart($event, item.key)"
              @click="previewTool(item.key)"
            >
              {{ item.label }}
              <i class="bi bi-plus-lg palette-item-add" @click.stop="addByClick(item.key)"></i>
            </button>
          </template>
        </template>

        <!-- 已存流程 -->
        <button class="palette-group saved-group palette-group-toggle" @click="toggleSection('__saved')">
          {{ t('pipeline.saved_recipes') }}
          <i class="bi" :class="isSectionOpen('__saved') ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
        </button>
        <template v-if="isSectionOpen('__saved')">
          <button class="palette-item" @click="store.newRecipe(); recipeName = ''">
            <i class="bi bi-file-earmark-plus me-1"></i>{{ t('pipeline.new_recipe') }}
          </button>
          <div v-for="r in store.savedRecipes" :key="r.id" class="saved-row">
            <button class="palette-item saved-item" :class="{ current: r.id === store.currentRecipeId }" @click="onOpen(r.id)">
              <i class="bi bi-diagram-3 me-1"></i>{{ r.name || t('pipeline.unnamed') }}
            </button>
            <i class="bi bi-trash saved-del" @click="store.deleteRecipe(r.id)"></i>
          </div>
        </template>
      </div>
    </template>

    <!-- 中:畫布（wrapper 承接 drop handler；canvas-flow 為 issue-bar 錨點 — spec §3.3） -->
    <template #center>
      <div class="canvas-wrap" @drop.prevent="onCanvasDrop" @dragover.prevent>
        <div class="canvas-flow">
        <VueFlow
          :nodes="flowNodes"
          :edges="flowEdges"
          :nodes-connectable="!store.running"
          :nodes-draggable="!store.running"
          @connect="onConnect"
          @node-drag-stop="onNodeDragStop"
          @node-click="onNodeClick"
          @edge-click="onEdgeClick"
        >
          <template #node-pipeline="{ id, data }">
            <div
              class="p-node"
              :class="{
                'is-input': data.kind === 'input',
                'is-source': data.kind === 'source',
                'has-error': data.hasError,
                'is-selected': data.selected,
                'is-running': data.runState === 'running',
                'is-run-failed': data.runState === 'failed',
                'is-run-done': data.runState === 'done',
              }"
              :title="data.titleAttr"
            >
              <Handle v-if="data.kind === 'tool'" type="target" :position="Position.Left" />
              <Handle type="source" :position="Position.Right" />
              <!-- hover 顯示的移除 badge；stop 防止觸發 node-click（選取/輸入節點開檔）與 drag。
                   輸入節點語意=清除已選檔案（無檔案時不顯示）；其餘節點=移除節點 -->
              <button
                v-if="!store.running && (data.kind !== 'input' || store.inputFiles.length > 0)"
                class="p-node-remove"
                :title="data.kind === 'input' ? t('pipeline.input_clear') : t('pipeline.remove_node')"
                @click.stop="onNodeRemoveClick(id, data.kind)"
                @mousedown.stop
              >
                <i class="bi bi-x"></i>
              </button>
              <div class="p-node-title">
                <i :class="['bi', data.kind === 'input' ? 'bi-folder2-open' : data.kind === 'source' ? 'bi-cloud-download' : 'bi-gear']"></i>
                {{ data.label }}
              </div>
            </div>
          </template>
        </VueFlow>

        <!-- 驗證訊息列 -->
        <div v-if="store.errors.length > 0" class="issue-bar">
          <i class="bi bi-exclamation-triangle me-1"></i>{{ store.errors[0].message }}
          <span v-if="store.errors.length > 1" class="issue-more">+{{ store.errors.length - 1 }}</span>
        </div>
        </div>

        <!-- 底部資訊列：目前縮放（沿其他工具 preview info bar 慣例） -->
        <AppMediaInfoBar :items="canvasInfoItems" />
      </div>
    </template>

    <!-- 右:參數面板 + run 控制 -->
    <template #right>
      <div class="config-content" :class="{ locked: store.running }">
        <PipelineParamForm
          v-if="store.selectedNode"
          :node="store.selectedNode"
          @update-params="(p) => store.updateNodeParams(store.selectedNode!.id, p)"
          @update-keep-output="(k) => store.setKeepOutput(store.selectedNode!.id, k)"
          @remove="store.removeNode(store.selectedNode!.id)"
        />
        <PipelineParamForm
          v-else-if="previewNode"
          :node="previewNode"
          preview
          @update-params="(p) => (previewParams = p)"
        />
        <p v-else class="config-empty">{{ t('pipeline.select_node_hint') }}</p>
      </div>

      <!-- run 控制 -->
      <div class="run-bar">
        <div class="save-row">
          <input
            v-model="recipeName"
            class="save-name"
            :placeholder="t('pipeline.recipe_name_placeholder')"
            :disabled="store.running"
          />
          <button class="save-btn" :disabled="saving || store.running" @click="onSave">
            <i class="bi bi-save"></i>
          </button>
        </div>
        <div v-if="rootIsInput" class="run-files">
          <button class="run-files-btn" :disabled="uploading || store.running" @click="fileInputRef?.click()">
            <i class="bi bi-file-earmark-plus me-1"></i>
            {{ uploading ? t('common.uploading') : t('pipeline.pick_files') }}
          </button>
          <input ref="fileInputRef" type="file" multiple hidden @change="onFilesPicked" />
          <div v-if="store.inputFiles.length" class="run-file-list">
            <span v-for="f in store.inputFiles" :key="f.fileId" class="run-file-chip">
              {{ f.filename }}
              <i class="bi bi-x" @click="removeInputFile(f.fileId)"></i>
            </span>
          </div>
        </div>

        <div v-if="store.runSnapshot" class="run-status">
          {{ runSummary }} — {{ t(`pipeline.status.${store.runSnapshot.status}`) }}
        </div>

        <button
          v-if="!store.running"
          class="run-btn"
          :disabled="!store.canRun"
          @click="store.startRun()"
        >
          <i class="bi bi-play-fill me-1"></i>{{ t('pipeline.run') }}
        </button>
        <button v-else class="run-btn cancel" @click="store.cancelRun()">
          <i class="bi bi-stop-fill me-1"></i>{{ t('common.cancel') }}
        </button>
      </div>
    </template>
  </AppThreePaneLayout>
</template>

<style lang="scss">
@import '@vue-flow/core/dist/style.css';
@import '@vue-flow/core/dist/theme-default.css';
</style>

<style lang="scss" scoped>
.locked { pointer-events: none; opacity: 0.55; }

// 節點盤（欄 chrome/寬度由 AppThreePaneLayout 擁有；wrapper 需 flex:1 + min-height:0
// 才能在殼的 flex column 內捲動而非撐高欄）
.palette {
  flex: 1;
  min-height: 0;
  padding: 1rem;
  padding-top: 0.5rem;
  overflow-y: auto;
}
// 群組標題:對齊 ToolLayout .function-group-label（字級/留白/分隔線一致）
.palette-group {
  padding: 0.5rem 0.75rem 0.15rem;
  font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
  color: var(--text-muted); letter-spacing: 0.05em;

  &:not(:first-child) {
    margin-top: 0.6rem;
    border-top: 1px solid var(--panel-border);
  }
}
// 折疊頭:沿用 palette-group 的小標籤外觀,補上可點/chevron
.palette-group-toggle {
  display: flex; align-items: center; gap: 0.35rem;
  width: 100%; background: transparent; border: none;
  text-align: left; cursor: pointer; font-family: inherit;
  &:hover { color: var(--text-primary); }
  i { font-size: 0.65rem; }
}
.palette-item {
  display: flex; align-items: center; gap: 0.5rem; width: 100%;
  padding: 0.6rem 0.75rem; margin-top: 0.25rem;
  background: transparent; border: none; border-radius: 8px;
  color: var(--text-muted); font-size: 0.9rem; text-align: left;
  cursor: grab; font-family: inherit;
  transition: all 0.15s ease;
  &:hover { color: var(--text-primary); background: var(--panel-bg-hover); }
  &.is-previewing { color: var(--text-primary); background: var(--panel-bg-active); }

  // hover/預覽中才浮現加號,平時保持與一般工具頁同樣乾淨的列表
  &:hover .palette-item-add, &.is-previewing .palette-item-add { opacity: 1; }
}
// 加號:置右、獨立點擊目標（點名字=右欄預覽選項,點 + 才加到畫布）
// 無底色:浮現時淺灰、自身 hover 亮起(text-primary=深色主題白/淺色主題黑)
.palette-item-add {
  margin-left: auto; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  width: 22px; height: 22px;
  font-size: 0.95rem; cursor: pointer; opacity: 0;
  color: var(--text-muted);
  transition: all 0.15s ease;
  &:hover { color: var(--text-primary); }
}

// 中欄 wrapper：撐滿（少 flex:1 → VueFlow height:100% 解析成 0）+ issue-bar 錨點
.canvas-wrap {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
// 畫布本體＋issue-bar 錨點；資訊列在其下方常駐（不被 issue-bar 蓋住）
.canvas-flow {
  flex: 1;
  min-height: 0;
  position: relative;
}

.issue-bar {
  position: absolute; left: 0; right: 0; bottom: 0;
  padding: 0.4rem 0.9rem;
  background: rgba(220, 53, 69, 0.12);
  border-top: 1px solid rgba(220, 53, 69, 0.4);
  color: var(--color-danger, #dc3545);
  font-size: 0.8rem;
}
.issue-more { margin-left: 0.5rem; opacity: 0.7; }

.config-content { flex: 1; padding: 1rem; overflow-y: auto; }
.config-empty { color: var(--text-muted); font-size: 0.85rem; }

.run-bar {
  padding: 0.75rem 1rem;
  border-top: 1px solid var(--panel-border);
  display: flex; flex-direction: column; gap: 0.6rem;
}
.run-files-btn {
  width: 100%; padding: 0.4rem;
  background: transparent; border: 1px dashed var(--panel-border);
  border-radius: 6px; color: var(--text-muted);
  font-size: 0.82rem; cursor: pointer; font-family: inherit;
  &:hover:not(:disabled) { color: var(--text-primary); border-color: var(--drop-zone-border-hover); }
  &:disabled { opacity: 0.5; }
}
.run-file-list { display: flex; flex-wrap: wrap; gap: 4px; max-height: 90px; overflow-y: auto; }
.run-file-chip {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 1px 6px; font-size: 0.72rem;
  background: var(--panel-bg-active); border-radius: 4px;
  color: var(--text-muted);
  i { cursor: pointer; &:hover { color: var(--color-danger, #dc3545); } }
}
.run-status { font-size: 0.78rem; color: var(--text-muted); }
.save-row { display: flex; gap: 0.4rem; }
.save-name {
  flex: 1; padding: 0.35rem 0.5rem;
  background: var(--input-bg); border: 1px solid var(--panel-border);
  border-radius: 6px; color: var(--text-primary);
  font-size: 0.82rem; font-family: inherit;
}
.save-btn {
  padding: 0.35rem 0.6rem;
  background: transparent; border: 1px solid var(--panel-border);
  border-radius: 6px; color: var(--text-muted); cursor: pointer;
  &:hover:not(:disabled) { color: var(--text-primary); }
  &:disabled { opacity: 0.5; }
}
.saved-group { margin-top: 1rem; }
.saved-row { display: flex; align-items: center; gap: 2px; }
.saved-item { flex: 1; &.current { color: var(--text-primary); background: var(--panel-bg-active); } }
.saved-del {
  padding: 0.3rem; color: var(--text-muted); cursor: pointer; font-size: 0.75rem;
  &:hover { color: var(--color-danger, #dc3545); }
}
.run-btn {
  width: 100%; padding: 0.6rem;
  background: var(--color-primary); border: none; border-radius: 8px;
  color: white; font-size: 0.9rem; cursor: pointer; font-family: inherit;
  &:hover:not(:disabled) { background: var(--color-primary-hover); }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
  &.cancel { background: var(--color-danger, #dc3545); }
}

// Vue Flow 自訂節點
.p-node {
  position: relative; // 移除 badge 的定位錨點
  min-width: 130px;
  padding: 0.5rem 0.7rem;
  background: var(--panel-bg-active, rgba(255,255,255,0.06));
  border: 1.5px solid var(--panel-border);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.8rem;

  // 輸入節點可點選檔——手型提示可互動（拖曳移動仍由 VueFlow 處理）
  &.is-input { border-color: var(--color-primary); cursor: pointer; }
  &.is-source { border-color: #2aa198; }
  &.has-error { border-color: var(--color-danger, #dc3545); }
  &.is-selected { box-shadow: 0 0 0 2px var(--color-primary); }

  // 執行狀態視覺（run 快照驅動；流程線不動）——tint 疊在 panel 底色上，深淺主題皆可讀
  &.is-run-done {
    background: color-mix(in srgb, var(--color-success) 22%, var(--panel-bg-active, rgba(255,255,255,0.06)));
    border-color: var(--color-success);
  }
  &.is-run-failed {
    background: color-mix(in srgb, var(--color-danger) 22%, var(--panel-bg-active, rgba(255,255,255,0.06)));
    border-color: var(--color-danger);
  }
  &.is-running {
    border-color: var(--color-primary);
    animation: p-node-pulse 1.2s ease-in-out infinite;
  }
}

// 執行中外框脈動（box-shadow 擴散淡出；持續動畫非 transition，沿執行中流光先例）
@keyframes p-node-pulse {
  0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--color-primary) 55%, transparent); }
  50%      { box-shadow: 0 0 0 6px color-mix(in srgb, var(--color-primary) 8%, transparent); }
}
.p-node-title { display: flex; align-items: center; gap: 0.4rem; }
// hover 顯示的移除 badge（樣式沿 AppFilmstrip 移除鈕慣例）
.p-node-remove {
  position: absolute;
  top: -8px;
  right: -8px;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  padding: 0;
  background: var(--color-danger);
  color: var(--text-primary);
  font-size: 0.75rem;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease, background 0.15s ease;

  &:hover {
    background: var(--color-danger-hover, color-mix(in srgb, var(--color-danger) 80%, black));
  }
}
.p-node:hover .p-node-remove {
  opacity: 1;
  pointer-events: auto;
}
</style>
