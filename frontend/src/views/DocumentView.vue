<script setup lang="ts">
import { ref, computed, watchEffect, onMounted, onUnmounted, onActivated, onDeactivated } from 'vue'
import { useI18n } from 'vue-i18n'
import ToolLayout from '@/components/ToolLayout.vue'
import AppFilmstrip from '@/components/common/AppFilmstrip.vue'
import DocumentPreview from '@/components/document/DocumentPreview.vue'
import AppMediaInfoBar, { type InfoItem } from '@/components/common/AppMediaInfoBar.vue'
import ToolParamHost from '@/components/params/ToolParamHost.vue'
import TextPreviewModal          from '@/components/common/TextPreviewModal.vue'
import { useDocumentWorkspace } from '@/composables/useDocumentWorkspace'
import { useMultiSubmit } from '@/composables/useMultiSubmit'
import { useExecuteStop } from '@/composables/useExecuteStop'
import { useTitlebar, type TitlebarExtraAction } from '@/composables/useTitlebar'
import { useViewHost } from '@/composables/useViewHost'
import { subfunctionsForView } from '@/agent/agentNavCatalog'
import { panelIdFor } from '@/composables/useActiveView'

const { t } = useI18n()

const {
  hasFile, fileId, isUploading, currentFileName, hasResult,
  textResultContent, textResultFilename,
  collection,
  handleFile, handleFiles, handleRemoveFile, handlePanelSubmit, handleDownload, handleDownloadBatch, handleTextDownload,
  handleExistingFiles,
} = useDocumentWorkspace()

const selectedIds = computed(() => collection.selectedIds.value)
const isMultiSelect = computed(() => selectedIds.value.size > 1)
const { submitToAll } = useMultiSubmit(collection)
const { isCanceling, requestStop } = useExecuteStop(collection)

// Panel refs
const translatePanelRef  = ref<InstanceType<typeof ToolParamHost>  | null>(null)
const pdfConvertPanelRef = ref<InstanceType<typeof ToolParamHost> | null>(null)
const ocrPanelRef        = ref<InstanceType<typeof ToolParamHost>        | null>(null)
const splitPanelRef      = ref<InstanceType<typeof ToolParamHost>      | null>(null)
const showOcrModal       = ref(false)

// ── W2：host 泛型收斂 ──────────────────────────────────────────────────────
// toolKey↔subFunction id 對映——四工具皆走 ToolParamHost，無非 host 例外殼。
const HOST_TOOL_KEYS: Record<string, string> = {
  translate: 'document.translate',
  'pdf-convert': 'document.pdf_convert',
  ocr: 'document.ocr',
  split: 'document.split',
}
const HOST_REFS: Record<string, typeof translatePanelRef> = {
  translate: translatePanelRef,
  'pdf-convert': pdfConvertPanelRef,
  ocr: ocrPanelRef,
  split: splitPanelRef,
}
function hostFor(fn: string) {
  return HOST_REFS[fn]?.value ?? null
}
const subFunctions = computed(() => [
  { id: 'split',       name: t('document.functions.split'),        icon: 'bi-layout-split',            group: t('document.group.edit') },
  { id: 'pdf-convert', name: t('document.functions.pdf_convert'),  icon: 'bi-file-earmark-pdf-fill',   group: t('document.group.edit') },
  { id: 'ocr',         name: t('document.functions.ocr'),          icon: 'bi-type',                    group: t('document.group.ai') },
  { id: 'translate',   name: t('document.functions.translate'),    icon: 'bi-translate',               group: t('document.group.ai') },
])

const currentFunction = ref('split')

useViewHost('document', {
  currentFunction,
  setCurrentFunction: (id) => { currentFunction.value = id },
  validSubfunctions: () => subfunctionsForView('document'),
  // document 無 activeFileId，用 fileId 當 active file id
  activeFile: computed(() =>
    fileId.value
      ? { id: fileId.value, name: currentFileName.value, kind: 'document' }
      : null,
  ),
})

const currentFileExt = computed(() => {
  const parts = currentFileName.value.split('.')
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : ''
})

// document.split 換檔清空 pages 的合成觸發源（見 split.meta.ts 檔頭「seedOnFileChange 觸發
// 源特例」註解）：document 領域無 /document/info 這類 fetch，沒有真正的 fileInfo 物件可餵。
// ToolParamHost 的 seed 唯一觸發源是 fileInfo prop 的 immediate watch，這裡用 fileId 包一個
// 最小合成物件——只借「fileId 變了→物件參考變了→watch 觸發」這件事，seedOnFileChange 本身
// 不讀取內容，只要被呼叫就無條件清空 pages（語意與舊 watch(fileId) 完全等價）。
const splitFileInfo = computed(() => (fileId.value ? { fileId: fileId.value } : null))

// document.ocr 副檔名限制（PDF 或圖片）——沿舊 DocumentOcrPanel.isPdfOrImage。ToolParamHost
// 的 validate 只吃 params 做不到這個判斷（需要檔名副檔名），故留在 View 層算，與 host 的
// isDisabled 用 || 合併（見下方 executeDisabled 'ocr' 分支）——批 4 Task 4.4 遷移決策，見
// components/params/document/OcrParams.vue 檔頭「isPdfOrImage」段落。
const isPdfOrImage = computed(() => {
  const ext = currentFileExt.value
  return ext === 'pdf' || ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff', 'tif'].includes(ext)
})

const isEntryProcessing = computed(() => collection.activeEntry.value?.status === 'processing')

const executeDisabled = computed(() => {
  const disabled = hostFor(currentFunction.value)?.isDisabled ?? !hasFile.value
  // ocr 副檔名限制（PDF/圖片）——host validate 判斷不到檔名副檔名，額外 || 合併（見上方
  // isPdfOrImage 註解）。
  if (currentFunction.value === 'ocr') return disabled || !isPdfOrImage.value
  return disabled
})

const executeLoading = computed(() => {
  if (isEntryProcessing.value) return true
  return hostFor(currentFunction.value)?.isLoading ?? false
})

function handleExecute() {
  if (isMultiSelect.value) {
    void handleMultiExecute()
  } else {
    handleSingleExecute()
  }
}

function handleSingleExecute() {
  hostFor(currentFunction.value)?.execute()
}

async function handleMultiExecute() {
  const noop = () => {}
  const fn = currentFunction.value
  const toolKey = HOST_TOOL_KEYS[fn]
  const host = hostFor(fn)
  if (!toolKey || !host) return
  // getSubmitSpec() 取代舊四工具一律 getParams()——四者皆無 buildSubmit，getSubmitSpec().payload
  // === {...params} 與 getParams() 完全等價（僅 apiPath/labelKey/taskType 從硬編字面值改讀
  // meta，值相同）。preflight 統一先行：無 modelRequirement 的工具（pdf-convert/split）恆真、
  // translate/ocr 與單筆 execute() 同語意，跟 VideoView 一致。
  if ((await host.preflight()) === false) return
  const spec = host.getSubmitSpec()
  await submitToAll(spec.apiPath, () => host.getSubmitSpec().payload, t(spec.labelKey), spec.taskType, noop)
}

function onDownload() {
  if (currentFunction.value === 'ocr') {
    handleTextDownload()
  } else {
    handleDownload()
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const documentInfoItems = computed<InfoItem[]>(() => {
  const entry = collection.activeEntry.value
  if (!entry) return []
  const ext = entry.fileName.split('.').pop()?.toUpperCase() ?? '—'
  return [
    { icon: 'bi-file-earmark-text', label: ext },
    { icon: 'bi-hdd',               label: formatSize(entry.fileSize) },
  ]
})

// ── Filmstrip ────────────────────────────────────────────────────────────────

const filmstripItems = computed(() =>
  collection.entriesList.value.map(e => ({
    id: e.id,
    thumbnailUrl: e.thumbnailUrl,
    status: e.status,
    progress: e.progress,
  }))
)

function onFilmstripSelect(id: string, ctrlKey: boolean) {
  collection.selectEntry(id, ctrlKey)
}

function onFilmstripRemove(id: string) {
  collection.removeEntry(id)
}

// ── Titlebar actions ──────────────────────────────────────────────────────
const { registerActions, clearActions, setExtraActions, clearExtraActions } = useTitlebar()

function registerTitlebar() {
  registerActions({
    canUndo: () => false,
    canRedo: () => false,
    canSaveAs: () => hasResult.value,
    onUndo: () => {},
    onRedo: () => {},
    onSaveAs: () => onDownload(),
  })
}

const _activeTick = ref(0)

watchEffect(() => {
  void _activeTick.value  // reactive dependency — forces re-run on increment
  const actions: TitlebarExtraAction[] = []
  if (currentFunction.value === 'ocr') {
    actions.push({
      id: 'text-preview',
      icon: 'bi-file-text',
      tooltip: t('common.view_ocr_result'),
      disabled: !textResultContent.value,
      onClick: () => { if (textResultContent.value) showOcrModal.value = true },
    })
  }
  setExtraActions(actions)
})

onActivated(() => { registerTitlebar(); _activeTick.value++ })
onDeactivated(() => { clearActions(); clearExtraActions() })
onMounted(() => { registerTitlebar() })
onUnmounted(() => { clearActions(); clearExtraActions() })
</script>

<template>
  <ToolLayout
    :title="$t('document.title')"
    accept-type="document"
    upload-icon="bi-file-earmark-text-fill"
    :upload-label="$t('document.upload_label')"
    :upload-hint="$t('document.upload_hint')"
    upload-accept=".pdf,.doc,.docx,.txt,.srt,.vtt,.md,.csv,.json"
    show-filmstrip
    :collection-size="filmstripItems.length"
    :active-file-name="currentFileName"
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-result="hasResult"
    :execute-disabled="executeDisabled"
    :execute-loading="executeLoading"
    :execute-canceling="isCanceling"
    @select-function="currentFunction = $event"
    @execute="handleExecute"
    @stop="requestStop"
    @file="handleFile"
    @files="handleFiles"
    @existing-files="handleExistingFiles"
    @remove-file="handleRemoveFile"
    @clear-selection="collection.clearSelection()"
  >

    <template #preview="{ file }">
      <DocumentPreview
        :file="collection.activeEntry.value?.file ?? file"
        :is-uploading="isUploading"
      />
    </template>

    <template #info-bar>
      <AppMediaInfoBar
        v-if="collection.activeEntry.value || isUploading"
        :items="documentInfoItems"
        :loading="isUploading"
        :loading-text="$t('document.loading')"
      />
    </template>

    <template #filmstrip>
      <AppFilmstrip
        :items="filmstripItems"
        :active-id="collection.activeId.value"
        :selected-ids="collection.selectedIds.value"
        @select="onFilmstripSelect"
        @remove="onFilmstripRemove"
        @remove-selected="ids => collection.removeEntries(ids)"
        @clear-selection="collection.clearSelection()"
        @select-all="collection.selectAll()"
        @batch-save="handleDownloadBatch"
      />
    </template>

    <template #settings>
      <div class="settings-form">
        <ToolParamHost
          v-if="currentFunction === 'translate'"
          ref="translatePanelRef"
          tool-key="document.translate"
          :panel-id="panelIdFor('document', 'translate')"
          :file-id="fileId"
          :current-file-name="currentFileName"
          :is-multi-select="isMultiSelect"
          @submit="handlePanelSubmit"
        />

        <ToolParamHost
          v-else-if="currentFunction === 'pdf-convert'"
          ref="pdfConvertPanelRef"
          tool-key="document.pdf_convert"
          :panel-id="panelIdFor('document', 'pdf-convert')"
          :current-file-ext="currentFileExt"
          :file-id="fileId"
          :current-file-name="currentFileName"
          :is-multi-select="isMultiSelect"
          @submit="handlePanelSubmit"
        />

        <template v-else-if="currentFunction === 'ocr'">
          <div v-if="!isPdfOrImage && hasFile" class="info-box info-box--warn">
            <i class="bi bi-info-circle"></i>
            <span>{{ $t('document.ocr.format_not_supported') }}</span>
          </div>
          <ToolParamHost
            ref="ocrPanelRef"
            tool-key="document.ocr"
            :panel-id="panelIdFor('document', 'ocr')"
            persist-key="doc_ocr_model"
            i18n-prefix="document.ocr"
            :file-id="fileId"
            :current-file-name="currentFileName"
            :is-multi-select="isMultiSelect"
            @submit="handlePanelSubmit"
          />
        </template>

        <ToolParamHost
          v-else-if="currentFunction === 'split'"
          ref="splitPanelRef"
          tool-key="document.split"
          :panel-id="panelIdFor('document', 'split')"
          :file-id="fileId"
          :file-info="splitFileInfo"
          :current-file-name="currentFileName"
          :is-multi-select="isMultiSelect"
          @submit="handlePanelSubmit"
        />
      </div>
    </template>
  </ToolLayout>

  <TextPreviewModal
    v-if="showOcrModal && textResultContent"
    :text="textResultContent"
    :title="$t('document.ocr.result_title')"
    :format="(ocrPanelRef?.outputFormat as 'md' | 'txt' | undefined) ?? 'md'"
    :filename="textResultFilename"
    @close="showOcrModal = false"
  />
</template>

<style lang="scss">
// document.ocr 副檔名警告（見 template ocr 分支）用共用 .info-box/.info-box--warn——
// 依 FRONTEND_DEVELOP_SPEC §24 不得在 scoped style 重複定義共用 class，改 @use 共用 partial。
@use '@/styles/tool-panels-shared';
</style>

<style lang="scss" scoped>
.settings-form { color: var(--text-primary); }

// 僅本 View 的版面間距（共用 .info-box 不帶 margin）。
.info-box { margin-bottom: 0.75rem; }
</style>
