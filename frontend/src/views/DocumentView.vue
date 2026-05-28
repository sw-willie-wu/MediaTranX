<script setup lang="ts">
import { ref, computed, watchEffect, onMounted, onUnmounted, onActivated, onDeactivated } from 'vue'
import { useI18n } from 'vue-i18n'
import ToolLayout from '@/components/ToolLayout.vue'
import AppFilmstrip from '@/components/common/AppFilmstrip.vue'
import DocumentPreview from '@/components/document/DocumentPreview.vue'
import AppMediaInfoBar, { type InfoItem } from '@/components/common/AppMediaInfoBar.vue'
import DocumentTranslatePanel   from '@/components/document/panels/DocumentTranslatePanel.vue'
import DocumentPdfConvertPanel  from '@/components/document/panels/DocumentPdfConvertPanel.vue'
import DocumentOcrPanel         from '@/components/document/panels/DocumentOcrPanel.vue'
import DocumentSplitPanel       from '@/components/document/panels/DocumentSplitPanel.vue'
import TextPreviewModal          from '@/components/common/TextPreviewModal.vue'
import { useDocumentWorkspace } from '@/composables/useDocumentWorkspace'
import { useMultiSubmit } from '@/composables/useMultiSubmit'
import { useTitlebar, type TitlebarExtraAction } from '@/composables/useTitlebar'
import { useViewHost } from '@/composables/useViewHost'

const { t } = useI18n()

const {
  hasFile, fileId, activeFileId, isUploading, currentFileName, hasResult,
  textResultContent, textResultFilename,
  collection,
  handleFile, handleFiles, handleRemoveFile, handlePanelSubmit, handleDownload, handleDownloadBatch, handleTextDownload,
  sourceDir,
} = useDocumentWorkspace()

const selectedIds = computed(() => collection.selectedIds.value)
const isMultiSelect = computed(() => selectedIds.value.size > 1)
const { isSubmitting, submitToAll } = useMultiSubmit(collection)

// Panel refs
const translatePanelRef  = ref<InstanceType<typeof DocumentTranslatePanel>  | null>(null)
const pdfConvertPanelRef = ref<InstanceType<typeof DocumentPdfConvertPanel> | null>(null)
const ocrPanelRef        = ref<InstanceType<typeof DocumentOcrPanel>        | null>(null)
const splitPanelRef      = ref<InstanceType<typeof DocumentSplitPanel>      | null>(null)
const showOcrModal       = ref(false)

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
  validSubfunctions: () => ['split', 'pdf-convert', 'ocr', 'translate'],
})

const currentFileExt = computed(() => {
  const parts = currentFileName.value.split('.')
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : ''
})

const isEntryProcessing = computed(() => collection.activeEntry.value?.status === 'processing')

const executeDisabled = computed(() => {
  if (currentFunction.value === 'translate')   return translatePanelRef.value?.isDisabled   ?? !hasFile.value
  if (currentFunction.value === 'pdf-convert') return pdfConvertPanelRef.value?.isDisabled  ?? !hasFile.value
  if (currentFunction.value === 'ocr')         return ocrPanelRef.value?.isDisabled         ?? !hasFile.value
  if (currentFunction.value === 'split')       return splitPanelRef.value?.isDisabled       ?? !hasFile.value
  return !hasFile.value
})

const executeLoading = computed(() => {
  if (isEntryProcessing.value) return true
  if (currentFunction.value === 'translate')   return translatePanelRef.value?.isLoading   ?? false
  if (currentFunction.value === 'pdf-convert') return pdfConvertPanelRef.value?.isLoading  ?? false
  if (currentFunction.value === 'ocr')         return ocrPanelRef.value?.isLoading         ?? false
  if (currentFunction.value === 'split')       return splitPanelRef.value?.isLoading       ?? false
  return false
})

function handleExecute() {
  if (isMultiSelect.value) {
    handleMultiExecute()
  } else {
    handleSingleExecute()
  }
}

function handleSingleExecute() {
  switch (currentFunction.value) {
    case 'translate':   translatePanelRef.value?.execute();   break
    case 'pdf-convert': pdfConvertPanelRef.value?.execute();  break
    case 'ocr':         ocrPanelRef.value?.execute();         break
    case 'split':       splitPanelRef.value?.execute();       break
  }
}

function handleMultiExecute() {
  const noop = () => {}
  switch (currentFunction.value) {
    case 'ocr':
      submitToAll('/document/ocr',         () => ocrPanelRef.value!.getParams(),        t('document.ocr.task_label'),         'document.ocr',         noop); break
    case 'translate':
      submitToAll('/document/translate',   () => translatePanelRef.value!.getParams(),  t('document.translate.task_label'),   'document.translate',   noop); break
    case 'split':
      submitToAll('/document/split',       () => splitPanelRef.value!.getParams(),      t('document.split.task_label'),       'document.split',       noop); break
    case 'pdf-convert':
      submitToAll('/document/pdf-convert', () => pdfConvertPanelRef.value!.getParams(), t('document.pdf_convert.task_label'), 'document.pdf_convert', noop); break
  }
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
  const ext = entry.file.name.split('.').pop()?.toUpperCase() ?? '—'
  return [
    { icon: 'bi-file-earmark-text', label: ext },
    { icon: 'bi-hdd',               label: formatSize(entry.file.size) },
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
  _activeTick.value
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
    @select-function="currentFunction = $event"
    @execute="handleExecute"
    @file="handleFile"
    @files="handleFiles"
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
        <DocumentTranslatePanel
          v-if="currentFunction === 'translate'"
          ref="translatePanelRef"
          :file-id="fileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
        />

        <DocumentPdfConvertPanel
          v-else-if="currentFunction === 'pdf-convert'"
          ref="pdfConvertPanelRef"
          :file-id="fileId"
          :current-file-name="currentFileName"
          :current-file-ext="currentFileExt"
          @submit="handlePanelSubmit"
        />

        <DocumentOcrPanel
          v-else-if="currentFunction === 'ocr'"
          ref="ocrPanelRef"
          :file-id="fileId"
          :current-file-name="currentFileName"
          :current-file-ext="currentFileExt"
          @submit="handlePanelSubmit"
        />

        <DocumentSplitPanel
          v-else-if="currentFunction === 'split'"
          ref="splitPanelRef"
          :file-id="fileId"
          :current-file-name="currentFileName"
          @submit="handlePanelSubmit"
        />
      </div>
    </template>
  </ToolLayout>

  <TextPreviewModal
    v-if="showOcrModal && textResultContent"
    :text="textResultContent"
    :title="$t('document.ocr.result_title')"
    :format="ocrPanelRef?.outputFormat ?? 'md'"
    :filename="textResultFilename"
    @close="showOcrModal = false"
  />
</template>

<style lang="scss" scoped>
.settings-form { color: var(--text-primary); }
</style>
