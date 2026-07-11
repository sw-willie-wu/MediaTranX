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
import PipelineParamForm from '@/components/pipeline/PipelineParamForm.vue'

const { t } = useI18n()
const store = usePipelineStore()
const filesStore = useFilesStore()
const toast = useToast()
const { screenToFlowCoordinate, fitView } = useVueFlow()

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
const flowNodes = computed(() =>
  store.recipe.nodes.map((n) => ({
    id: n.id,
    type: 'pipeline',
    position: n.position ?? { x: 100, y: 100 },
    data: {
      kind: n.kind,
      toolKey: n.toolKey,
      label: n.kind === 'input' ? t('pipeline.input_node') : t(TOOL_REGISTRY[n.toolKey!]?.labelKey ?? n.toolKey!),
      hasError: store.errors.some(i => i.nodeId === n.id),
      agg: nodeAgg(n.id),
      selected: store.selectedNodeId === n.id,
    },
  })),
)

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

function onNodeClick(e: { node: { id: string } }) {
  store.selectedNodeId = e.node.id
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
  store.addToolNode(toolKey, { x: 80 + idx * 190, y: 180 + (idx % 2) * 90 })
  setTimeout(() => fitView({ padding: 0.25 }), 50)
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
      const fileId = await filesStore.uploadFile(f)
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
  setTimeout(() => fitView({ padding: 0.25 }), 80)
}
</script>

<template>
  <AppThreePaneLayout>
    <!-- 左:節點盤（run 中鎖定；欄 chrome 由殼擁有） -->
    <template #left>
      <div class="palette" :class="{ locked: store.running }">
        <h6 class="palette-title">{{ t('pipeline.palette_title') }}</h6>
        <template v-for="(items, domain) in paletteGroups" :key="domain">
          <button class="palette-group palette-group-toggle" @click="toggleSection(domain)">
            <i class="bi" :class="isSectionOpen(domain) ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
            {{ t(`nav.${domain}`) }}
          </button>
          <template v-if="isSectionOpen(domain)">
            <button
              v-for="item in items"
              :key="item.key"
              class="palette-item"
              draggable="true"
              @dragstart="onPaletteDragStart($event, item.key)"
              @click="addByClick(item.key)"
            >
              <i class="bi bi-plus-square me-1"></i>{{ item.label }}
            </button>
          </template>
        </template>

        <!-- 已存流程 -->
        <button class="palette-group saved-group palette-group-toggle" @click="toggleSection('__saved')">
          <i class="bi" :class="isSectionOpen('__saved') ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
          {{ t('pipeline.saved_recipes') }}
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

    <!-- 中:畫布（wrapper 承接 drop handler + issue-bar 錨點 — spec §3.3） -->
    <template #center>
      <div class="canvas-wrap" @drop.prevent="onCanvasDrop" @dragover.prevent>
        <VueFlow
          :nodes="flowNodes"
          :edges="flowEdges"
          :nodes-connectable="!store.running"
          :nodes-draggable="!store.running"
          fit-view-on-init
          @connect="onConnect"
          @node-drag-stop="onNodeDragStop"
          @node-click="onNodeClick"
          @edge-click="onEdgeClick"
        >
          <template #node-pipeline="{ data }">
            <div
              class="p-node"
              :class="{
                'is-input': data.kind === 'input',
                'is-source': data.kind === 'source',
                'has-error': data.hasError,
                'is-selected': data.selected,
              }"
            >
              <Handle v-if="data.kind === 'tool'" type="target" :position="Position.Left" />
              <Handle type="source" :position="Position.Right" />
              <div class="p-node-title">
                <i :class="['bi', data.kind === 'input' ? 'bi-folder2-open' : data.kind === 'source' ? 'bi-cloud-download' : 'bi-gear']"></i>
                {{ data.label }}
              </div>
              <div v-if="data.agg" class="p-node-status" :class="{ failed: data.agg.failed > 0, active: data.agg.active }">
                {{ data.agg.done }}/{{ data.agg.total }}
                <span v-if="data.agg.failed > 0">({{ data.agg.failed }}✗)</span>
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
  padding: 0.75rem;
  overflow-y: auto;
}
.palette-title { font-size: 0.85rem; color: var(--text-primary); margin: 0 0 0.5rem; }
.palette-group {
  margin-top: 0.6rem; padding: 0.25rem 0.35rem 0.1rem;
  font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
  color: var(--text-muted); letter-spacing: 0.05em;
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
  display: block; width: 100%;
  padding: 0.4rem 0.5rem; margin-top: 2px;
  background: transparent; border: none; border-radius: 6px;
  color: var(--text-muted); font-size: 0.82rem; text-align: left;
  cursor: grab; font-family: inherit;
  &:hover { color: var(--text-primary); background: var(--panel-bg-hover); }
}

// 中欄 wrapper：撐滿（少 flex:1 → VueFlow height:100% 解析成 0）+ issue-bar 錨點
.canvas-wrap {
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
.saved-group { margin-top: 1rem; border-top: 1px solid var(--panel-border); padding-top: 0.6rem; }
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
  min-width: 130px;
  padding: 0.5rem 0.7rem;
  background: var(--panel-bg-active, rgba(255,255,255,0.06));
  border: 1.5px solid var(--panel-border);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.8rem;

  &.is-input { border-color: var(--color-primary); }
  &.is-source { border-color: #2aa198; }
  &.has-error { border-color: var(--color-danger, #dc3545); }
  &.is-selected { box-shadow: 0 0 0 2px var(--color-primary); }
}
.p-node-title { display: flex; align-items: center; gap: 0.4rem; }
.p-node-status {
  margin-top: 0.3rem; font-size: 0.7rem; color: var(--text-muted);
  &.active { color: var(--color-primary); }
  &.failed { color: var(--color-danger, #dc3545); }
}
</style>
