<script setup lang="ts">
import { ref, watch } from 'vue'
import ToolLayout from '@/components/ToolLayout.vue'
import AppMediaInfoBar from '@/components/common/AppMediaInfoBar.vue'
import DocumentTranslatePanel from '@/components/document/panels/DocumentTranslatePanel.vue'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { useFileDownload } from '@/composables/useFileDownload'

const subFunctions = [
  { id: 'translate', name: '翻譯', icon: 'bi-translate' },
  { id: 'pdf-convert', name: 'PDF 轉換', icon: 'bi-file-earmark-pdf-fill', comingSoon: true },
  { id: 'ocr', name: '文字辨識', icon: 'bi-type', comingSoon: true },
  { id: 'merge', name: '合併文件', icon: 'bi-union', comingSoon: true },
  { id: 'split', name: '分割文件', icon: 'bi-layout-split', comingSoon: true },
]

const currentFunction = ref('translate')

const filesStore = useFilesStore()
const taskStore = useTaskStore()
const toast = useToast()
const { downloadFile } = useFileDownload()

const currentTranslateTaskId = ref<string | null>(null)

const hasFile = ref(false)
const hasResult = ref(false)
const currentFileName = ref('')
const sourceDir = ref<string | undefined>(undefined)
const fileId = ref<string | null>(null)
const isUploading = ref(false)

function selectFunction(id: string) {
  currentFunction.value = id
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function getDocInfoItems(file: File) {
  const ext = file.name.split('.').pop()?.toUpperCase() ?? '—'
  return [
    { icon: 'bi-file-earmark-text', label: ext },
    { icon: 'bi-hdd', label: formatSize(file.size) },
  ]
}

async function handleFile(file: File, srcDir?: string) {
  hasFile.value = true
  currentFileName.value = file.name
  sourceDir.value = srcDir
  isUploading.value = true

  try {
    const id = await filesStore.uploadFile(file, srcDir)
    fileId.value = id
  } catch (e) {
    fileId.value = null
  } finally {
    isUploading.value = false
  }
}

function handleTranslateSubmit(taskId: string) {
  currentTranslateTaskId.value = taskId
}

function handleDownload() {
  const task = currentTranslateTaskId.value ? taskStore.tasks.get(currentTranslateTaskId.value) : null
  if (!task?.result) return
  const r = task.result as { output_file_id?: string }
  if (!r.output_file_id) return
  const baseName = currentFileName.value.replace(/\.[^.]+$/, '')
  downloadFile(r.output_file_id, `${baseName}_translated.srt`, sourceDir.value)
}

// 監聽翻譯任務完成 → 帶下載的 toast
watch(
  () => currentTranslateTaskId.value ? taskStore.tasks.get(currentTranslateTaskId.value) : null,
  (task) => {
    if (!task || task.status !== 'completed' || !task.result) return
    const r = task.result as { output_file_id?: string }
    if (!r.output_file_id) return
    hasResult.value = true
    toast.show('文件翻譯完成', {
      type: 'success',
      icon: 'bi-check-circle',
      action: { label: '下載', callback: () => handleDownload() },
    })
  },
  { deep: true }
)
</script>

<template>
  <ToolLayout
    title="文件工具"
    accept-type="document"
    upload-icon="bi-file-earmark-text-fill"
    upload-label="拖曳文件到這裡"
    upload-accept=".pdf,.doc,.docx,.txt,.srt,.vtt,.md,.csv,.json"
    hide-preview-tabs
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-result="hasResult"
    @select-function="selectFunction"
    @file="handleFile"
    @download="handleDownload"
  >
    <!-- 預覽區域 -->
    <template #preview="{ file }">
      <div class="preview-display">
        <div class="document-preview">
          <i class="bi bi-file-earmark-text-fill"></i>
          <p class="filename">{{ file.name }}</p>
          <p v-if="isUploading" class="upload-hint">上傳中...</p>
        </div>
        <AppMediaInfoBar
          :items="getDocInfoItems(file)"
          :loading="isUploading"
          loading-text="上傳中..."
        />
      </div>
    </template>

    <!-- 設定面板 -->
    <template #settings>
      <div class="settings-form">
        <DocumentTranslatePanel
          v-if="currentFunction === 'translate'"
          :file-id="fileId"
          :current-file-name="currentFileName"
          @submit="handleTranslateSubmit"
        />

        <div v-else class="function-settings">
          <h6 class="settings-title">
            <i
              class="bi me-2"
              :class="{
                'bi-file-earmark-pdf-fill': currentFunction === 'pdf-convert',
                'bi-type': currentFunction === 'ocr',
                'bi-union': currentFunction === 'merge',
                'bi-layout-split': currentFunction === 'split',
              }"
            ></i>
            {{ { 'pdf-convert': 'PDF 轉換', ocr: '文字辨識 (OCR)', merge: '合併文件', split: '分割文件' }[currentFunction] }}
          </h6>
          <p class="text-muted">即將推出</p>
        </div>
      </div>
    </template>
  </ToolLayout>
</template>

<style lang="scss" scoped>
.preview-display {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.document-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  padding: 2rem;
  background: var(--input-bg);
  border-radius: 16px;

  i {
    font-size: 4rem;
    color: var(--color-info);
  }

  .filename {
    color: var(--text-primary);
    font-size: 1rem;
  }

  .upload-hint {
    color: var(--text-muted);
    font-size: 0.85rem;
  }
}

.settings-form { color: var(--text-primary); }

.function-settings {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.settings-title {
  display: flex;
  align-items: center;
  font-size: 1rem;
  font-weight: 500;
  margin: 0;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--panel-border);
}

.text-muted { color: var(--text-muted); }
</style>
