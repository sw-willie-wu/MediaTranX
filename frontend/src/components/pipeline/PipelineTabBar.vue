<script setup lang="ts">
/**
 * 畫布分頁列（spec §3）——多文件 tab，視覺沿 AudioMidiEditPanel .settings-tabs。
 * 關閉非空分頁走 useConfirm() 全域確認單例（AppConfirmDialog 是 App.vue 掛的
 * 單例、不收 props——別自行 mount）；跑中分頁 × disabled；雙擊 inline 改名。
 */
import { nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { MAX_DOCS, usePipelineStore } from '@/stores/pipeline'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'

const { t } = useI18n()
const store = usePipelineStore()
const toast = useToast()
const { confirm } = useConfirm()

const editingId = ref<string | null>(null)
const editName = ref('')
const editInputRef = ref<HTMLInputElement[]>([])

function onAdd() {
  if (store.newDoc() === null) {
    toast.show(t('pipeline.tab_limit'), { type: 'error', icon: 'bi-x-circle' })
  }
}

async function onCloseClick(id: string) {
  const tab = store.tabs.find(x => x.id === id)
  if (!tab || tab.running) return
  if (store.isBlankDocId(id)) { store.closeDoc(id); return }
  if (await confirm({ title: t('pipeline.tab_close'), message: t('pipeline.tab_close_confirm'), type: 'warning' })) {
    store.closeDoc(id)
  }
}

function startRename(id: string, current: string) {
  editingId.value = id
  editName.value = current
  void nextTick(() => editInputRef.value[0]?.select())
}

function commitRename() {
  if (editingId.value !== null) store.renameDoc(editingId.value, editName.value.trim())
  editingId.value = null
}
</script>

<template>
  <div class="pipeline-tabs">
    <div
      v-for="tab in store.tabs"
      :key="tab.id"
      class="pipeline-tab"
      :class="{ 'is-active': tab.active }"
      @click="store.activeDocId = tab.id"
      @dblclick="startRename(tab.id, tab.name)"
    >
      <i v-if="tab.running" class="bi bi-arrow-repeat tab-spin"></i>
      <input
        v-if="editingId === tab.id"
        ref="editInputRef"
        v-model="editName"
        class="tab-rename"
        @keydown.enter="commitRename"
        @keydown.esc="editingId = null"
        @blur="commitRename"
        @click.stop
        @dblclick.stop
      />
      <span v-else class="tab-name">{{ tab.name || t('pipeline.titlebar_unnamed') }}</span>
      <button
        class="tab-close"
        :disabled="tab.running"
        :title="tab.running ? t('pipeline.tab_running_no_close') : t('pipeline.tab_close')"
        @click.stop="onCloseClick(tab.id)"
      ><i class="bi bi-x"></i></button>
    </div>
    <button
      class="tab-add"
      :disabled="store.tabs.length >= MAX_DOCS"
      :title="t('pipeline.tab_new')"
      @click="onAdd"
    ><i class="bi bi-plus-lg"></i></button>
  </div>
</template>

<style lang="scss" scoped>
// 視覺沿 AudioMidiEditPanel .settings-tabs（頂部 tab 條、底線 active 指示）
.pipeline-tabs {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 6px 10px 0;
  border-bottom: 1px solid var(--panel-border);
  overflow-x: auto;
  scrollbar-width: none;
  flex-shrink: 0;
}

.pipeline-tab {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  padding: 5px 6px 5px 12px;
  max-width: 180px;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  user-select: none;
  transition: color 0.15s ease, border-color 0.15s ease;
  white-space: nowrap;

  &:hover { color: var(--text-primary); }

  &.is-active {
    color: var(--text-primary);
    border-bottom-color: var(--color-primary);
  }
}

.tab-name {
  overflow: hidden;
  text-overflow: ellipsis;
}

.tab-rename {
  width: 110px;
  padding: 0 4px;
  font-size: 13px;
  font-family: inherit;
  color: var(--text-primary);
  background: var(--panel-bg);
  border: 1px solid var(--color-primary);
  border-radius: 4px;
  outline: none;
}

.tab-spin {
  color: var(--color-primary);
  animation: tab-icon-spin 1s linear infinite;
  flex-shrink: 0;
}
@keyframes tab-icon-spin {
  to { transform: rotate(360deg); }
}

.tab-close,
.tab-add {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;

  &:hover:not(:disabled) {
    color: var(--text-primary);
    background: var(--panel-bg-hover);
  }
  &:disabled { opacity: 0.4; cursor: default; }
}

.tab-add {
  padding: 4px 8px;
  margin-bottom: 2px;
  flex-shrink: 0;
}
</style>
