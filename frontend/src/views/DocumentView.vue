<script setup lang="ts">
import { ref, computed } from 'vue'
import ToolLayout from '@/components/ToolLayout.vue'
import DocumentPreview from '@/components/document/DocumentPreview.vue'
import AppMediaInfoBar, { type InfoItem } from '@/components/common/AppMediaInfoBar.vue'
import DocumentTranslatePanel   from '@/components/document/panels/DocumentTranslatePanel.vue'
import DocumentPdfConvertPanel  from '@/components/document/panels/DocumentPdfConvertPanel.vue'
import DocumentOcrPanel         from '@/components/document/panels/DocumentOcrPanel.vue'
import DocumentSplitPanel       from '@/components/document/panels/DocumentSplitPanel.vue'
import OcrResultModal           from '@/components/image/OcrResultModal.vue'
import { useDocumentWorkspace } from '@/composables/useDocumentWorkspace'

const {
  hasFile, fileId, isUploading, currentFileName, hasResult,
  textResultContent, textResultFilename,
  handleFile, handleRemoveFile, handlePanelSubmit, handleDownload, handleTextDownload,
} = useDocumentWorkspace()

// Panel refs
const translatePanelRef  = ref<InstanceType<typeof DocumentTranslatePanel>  | null>(null)
const pdfConvertPanelRef = ref<InstanceType<typeof DocumentPdfConvertPanel> | null>(null)
const ocrPanelRef        = ref<InstanceType<typeof DocumentOcrPanel>        | null>(null)
const splitPanelRef      = ref<InstanceType<typeof DocumentSplitPanel>      | null>(null)
const showOcrModal       = ref(false)

const subFunctions = [
  { id: 'translate',   name: '翻譯',     icon: 'bi-translate' },
  { id: 'pdf-convert', name: 'PDF 轉換', icon: 'bi-file-earmark-pdf-fill' },
  { id: 'ocr',         name: '文字辨識', icon: 'bi-type' },
  { id: 'split',       name: '分割文件', icon: 'bi-layout-split' },
]

const currentFunction = ref('translate')

const currentFileExt = computed(() => {
  const parts = currentFileName.value.split('.')
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : ''
})

const executeDisabled = computed(() => {
  if (currentFunction.value === 'translate')   return translatePanelRef.value?.isDisabled   ?? !hasFile.value
  if (currentFunction.value === 'pdf-convert') return pdfConvertPanelRef.value?.isDisabled  ?? !hasFile.value
  if (currentFunction.value === 'ocr')         return ocrPanelRef.value?.isDisabled         ?? !hasFile.value
  if (currentFunction.value === 'split')       return splitPanelRef.value?.isDisabled       ?? !hasFile.value
  return !hasFile.value
})

const executeLoading = computed(() => {
  if (currentFunction.value === 'translate')   return translatePanelRef.value?.isLoading   ?? false
  if (currentFunction.value === 'pdf-convert') return pdfConvertPanelRef.value?.isLoading  ?? false
  if (currentFunction.value === 'ocr')         return ocrPanelRef.value?.isLoading         ?? false
  if (currentFunction.value === 'split')       return splitPanelRef.value?.isLoading       ?? false
  return false
})

function handleExecute() {
  switch (currentFunction.value) {
    case 'translate':   translatePanelRef.value?.execute();   break
    case 'pdf-convert': pdfConvertPanelRef.value?.execute();  break
    case 'ocr':         ocrPanelRef.value?.execute();         break
    case 'split':       splitPanelRef.value?.execute();       break
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

const currentFile = ref<File | null>(null)

const documentInfoItems = computed<InfoItem[]>(() => {
  if (!currentFile.value) return []
  const ext = currentFile.value.name.split('.').pop()?.toUpperCase() ?? '—'
  return [
    { icon: 'bi-file-earmark-text', label: ext },
    { icon: 'bi-hdd',               label: formatSize(currentFile.value.size) },
  ]
})

function onFile(file: File, sourceDir?: string) {
  currentFile.value = file
  handleFile(file, sourceDir)
}

function onRemoveFile() {
  currentFile.value = null
  handleRemoveFile()
}
</script>

<template>
  <ToolLayout
    title="文件工具"
    accept-type="document"
    upload-icon="bi-file-earmark-text-fill"
    upload-label="拖曳文件到這裡"
    upload-hint="支援 PDF、DOCX、TXT、SRT 等格式"
    upload-accept=".pdf,.doc,.docx,.txt,.srt,.vtt,.md,.csv,.json"
    hide-preview-tabs
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-result="hasResult"
    :execute-disabled="executeDisabled"
    :execute-loading="executeLoading"
    @select-function="currentFunction = $event"
    @execute="handleExecute"
    @file="onFile"
    @remove-file="onRemoveFile"
    @download="onDownload"
  >
    <template #toolbar-extra>
      <button
        v-if="currentFunction === 'ocr' && textResultContent"
        class="toolbar-btn ocr-result-btn"
        data-tooltip="查看 OCR 結果"
        @click="showOcrModal = true"
      >
        <i class="bi bi-file-text"></i>
      </button>
    </template>

    <template #preview="{ file }">
      <DocumentPreview :file="file" :is-uploading="isUploading" />
    </template>

    <template #info-bar>
      <AppMediaInfoBar
        v-if="currentFile || isUploading"
        :items="documentInfoItems"
        :loading="isUploading"
        loading-text="上傳中..."
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

  <OcrResultModal
    v-if="showOcrModal && textResultContent"
    :text="textResultContent"
    :format="ocrPanelRef?.outputFormat ?? 'md'"
    :filename="textResultFilename"
    @close="showOcrModal = false"
  />
</template>

<style lang="scss" scoped>
.settings-form { color: var(--text-primary); }
</style>
