<script setup lang="ts">
import { ref, computed } from 'vue'
import ToolLayout from '@/components/ToolLayout.vue'

// 子功能列表
const subFunctions = [
  { id: 'pdf-convert', name: 'PDF 轉換', icon: 'bi-file-earmark-pdf-fill' },
  { id: 'ocr', name: '文字辨識', icon: 'bi-type' },
  { id: 'merge', name: '合併文件', icon: 'bi-union' },
  { id: 'split', name: '分割文件', icon: 'bi-layout-split' },
]

const currentFunction = ref('pdf-convert')

// 檔案狀態
const currentFile = ref<File | null>(null)
const hasFile = computed(() => !!currentFile.value)
const hasResult = ref(false)

function selectFunction(id: string) {
  currentFunction.value = id
}

function handleExport() {
  console.log('Export document')
}

function handleDrop(e: DragEvent) {
  e.preventDefault()
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    currentFile.value = files[0]
  }
}
</script>

<template>
  <ToolLayout
    title="文件工具"
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-file="hasFile"
    :has-result="hasResult"
    @select-function="selectFunction"
    @export="handleExport"
  >
    <!-- 預覽區域 -->
    <template #preview>
      <div
        v-if="!hasFile"
        class="upload-zone"
        @dragover.prevent
        @drop="handleDrop"
      >
        <i class="bi bi-file-earmark-text-fill"></i>
        <p>拖曳文件到這裡</p>
        <p class="hint">支援 PDF、Word 等格式</p>
      </div>

      <div v-else class="preview-display">
        <div class="document-preview">
          <i class="bi bi-file-earmark-text-fill"></i>
          <p class="filename">{{ currentFile?.name }}</p>
        </div>
      </div>
    </template>

    <!-- 設定面板 -->
    <template #settings>
      <div class="settings-form">
        <div v-if="currentFunction === 'pdf-convert'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-file-earmark-pdf-fill me-2"></i>PDF 轉換
          </h6>
          <p class="text-muted">即將推出</p>
        </div>

        <div v-if="currentFunction === 'ocr'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-type me-2"></i>文字辨識 (OCR)
          </h6>
          <p class="text-muted">即將推出</p>
        </div>

        <div v-if="currentFunction === 'merge'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-union me-2"></i>合併文件
          </h6>
          <p class="text-muted">即將推出</p>
        </div>

        <div v-if="currentFunction === 'split'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-layout-split me-2"></i>分割文件
          </h6>
          <p class="text-muted">即將推出</p>
        </div>
      </div>
    </template>
  </ToolLayout>
</template>

<style lang="scss" scoped>
.upload-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  border: 2px dashed var(--drop-zone-border);
  border-radius: 12px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    border-color: var(--drop-zone-border-hover);
    background: var(--input-bg);
  }

  i { font-size: 3rem; margin-bottom: 1rem; }
  p { margin: 0; font-size: 1rem; }
  .hint { font-size: 0.85rem; margin-top: 0.5rem; }
}

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
