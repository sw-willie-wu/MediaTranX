<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import ToolLayout from '@/components/ToolLayout.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'
import AppUploadZone from '@/components/common/AppUploadZone.vue'
import { useFilesStore } from '@/stores/files'

const filesStore = useFilesStore()

// 從 File 物件提取來源目錄（透過 preload 快取）
function extractSourceDir(file: File): string | undefined {
  return window.electron?.getFileSourceDir?.(file.name, file.size, file.lastModified) ?? undefined
}

// 檢查是否有從首頁拖曳過來的檔案
onMounted(() => {
  const pending = filesStore.consumePendingFile()
  if (pending) {
    loadFile(pending.file, pending.sourceDir)
  }
})

// 子功能列表
const subFunctions = [
  { id: 'remove-bg', name: '去背', icon: 'bi-eraser-fill' },
  { id: 'upscale', name: '超解析', icon: 'bi-arrows-angle-expand' },
  { id: 'filter', name: '濾鏡', icon: 'bi-palette-fill' },
  { id: 'convert', name: '轉檔', icon: 'bi-arrow-repeat' },
  { id: 'crop', name: '裁切', icon: 'bi-crop' },
  { id: 'compress', name: '壓縮', icon: 'bi-file-zip-fill' },
]

// 當前選擇的功能
const currentFunction = ref('remove-bg')

// 檔案狀態
const currentFile = ref<File | null>(null)
const originalPreview = ref<string | null>(null)
const resultPreview = ref<string | null>(null)
const isProcessing = ref(false)

const hasFile = computed(() => !!currentFile.value)
const hasResult = computed(() => !!resultPreview.value)

// 去背設定
const removeBgMode = ref('auto')
const removeBgModes = [
  { value: 'auto', label: '自動偵測' },
  { value: 'person', label: '人物' },
  { value: 'product', label: '商品' },
  { value: 'animal', label: '動物' },
]

// 超解析設定
const upscaleScale = ref(2)
const upscaleScales = [
  { value: 2, label: '2x' },
  { value: 4, label: '4x' },
]

// 轉檔設定
const convertFormat = ref('png')
const convertQuality = ref(90)
const convertFormats = [
  { value: 'png', label: 'PNG' },
  { value: 'jpg', label: 'JPEG' },
  { value: 'webp', label: 'WebP' },
  { value: 'gif', label: 'GIF' },
]

function selectFunction(id: string) {
  currentFunction.value = id
}

function handleExport() {
  // TODO: 實作匯出功能
  console.log('Export')
}

function executeProcess() {
  // TODO: 執行處理
  isProcessing.value = true
  setTimeout(() => {
    isProcessing.value = false
    // 模擬處理結果
    resultPreview.value = originalPreview.value
  }, 2000)
}

// 拖曳上傳
function handleDrop(e: DragEvent) {
  e.preventDefault()
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    loadFile(files[0])
  }
}

const sourceDir = ref<string | undefined>(undefined)

function loadFile(file: File, srcDir?: string) {
  currentFile.value = file
  sourceDir.value = srcDir
  const reader = new FileReader()
  reader.onload = (e) => {
    originalPreview.value = e.target?.result as string
  }
  reader.readAsDataURL(file)
  resultPreview.value = null
}
</script>

<template>
  <ToolLayout
    title="圖片工具"
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-file="hasFile"
    :has-result="hasResult"
    @select-function="selectFunction"
    @export="handleExport"
  >
    <!-- 預覽區域 -->
    <template #preview="{ mode }">
      <AppUploadZone
        v-if="!hasFile"
        icon="bi-cloud-arrow-up-fill"
        label="拖曳圖片到這裡"
        accept="image/*"
        @file="loadFile"
      />

      <div v-else class="preview-display" :class="{ compare: mode === 'compare' }">
        <div v-if="mode === 'original' || mode === 'compare'" class="preview-image">
          <img :src="originalPreview" alt="原圖" />
          <span v-if="mode === 'compare'" class="label">原圖</span>
        </div>
        <div v-if="(mode === 'result' || mode === 'compare') && hasResult" class="preview-image">
          <img :src="resultPreview" alt="成果" />
          <span v-if="mode === 'compare'" class="label">成果</span>
        </div>
        <div v-if="mode === 'result' && !hasResult" class="no-result">
          <i class="bi bi-hourglass"></i>
          <p>尚未處理</p>
        </div>
      </div>
    </template>

    <!-- 設定面板 -->
    <template #settings>
      <div class="settings-form">
        <!-- 去背設定 -->
        <div v-if="currentFunction === 'remove-bg'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-eraser-fill me-2"></i>去背設定
          </h6>

          <div class="form-group">
            <label>模式</label>
            <AppSelect v-model="removeBgMode" :options="removeBgModes" />
          </div>

          <button
            class="execute-btn"
            :disabled="!hasFile || isProcessing"
            @click="executeProcess"
          >
            <span v-if="isProcessing" class="spinner-border spinner-border-sm me-2"></span>
            {{ isProcessing ? '處理中...' : '執行去背' }}
          </button>
        </div>

        <!-- 超解析設定 -->
        <div v-if="currentFunction === 'upscale'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-arrows-angle-expand me-2"></i>超解析設定
          </h6>

          <div class="form-group">
            <label>放大倍數</label>
            <div class="scale-options">
              <button
                v-for="s in upscaleScales"
                :key="s.value"
                class="scale-btn"
                :class="{ active: upscaleScale === s.value }"
                @click="upscaleScale = s.value"
              >
                {{ s.label }}
              </button>
            </div>
          </div>

          <button
            class="execute-btn"
            :disabled="!hasFile || isProcessing"
            @click="executeProcess"
          >
            <span v-if="isProcessing" class="spinner-border spinner-border-sm me-2"></span>
            {{ isProcessing ? '處理中...' : '執行超解析' }}
          </button>
        </div>

        <!-- 轉檔設定 -->
        <div v-if="currentFunction === 'convert'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-arrow-repeat me-2"></i>轉檔設定
          </h6>

          <div class="form-group">
            <label>輸出格式</label>
            <AppSelect v-model="convertFormat" :options="convertFormats" />
          </div>

          <div class="form-group" v-if="convertFormat === 'jpg' || convertFormat === 'webp'">
            <label>品質: {{ convertQuality }}%</label>
            <AppRange v-model="convertQuality" :min="1" :max="100" />
          </div>

          <button
            class="execute-btn"
            :disabled="!hasFile || isProcessing"
            @click="executeProcess"
          >
            <span v-if="isProcessing" class="spinner-border spinner-border-sm me-2"></span>
            {{ isProcessing ? '處理中...' : '執行轉檔' }}
          </button>
        </div>

        <!-- 濾鏡設定 -->
        <div v-if="currentFunction === 'filter'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-palette-fill me-2"></i>濾鏡設定
          </h6>
          <p class="text-muted">即將推出</p>
        </div>

        <!-- 裁切設定 -->
        <div v-if="currentFunction === 'crop'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-crop me-2"></i>裁切設定
          </h6>
          <p class="text-muted">即將推出</p>
        </div>

        <!-- 壓縮設定 -->
        <div v-if="currentFunction === 'compress'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-file-zip-fill me-2"></i>壓縮設定
          </h6>
          <p class="text-muted">即將推出</p>
        </div>
      </div>
    </template>
  </ToolLayout>
</template>

<style lang="scss" scoped>
// 預覽顯示
.preview-display {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  gap: 1rem;

  &.compare {
    .preview-image {
      flex: 1;
      max-width: 50%;
    }
  }
}

.preview-image {
  position: relative;
  max-width: 100%;
  max-height: 100%;

  img {
    max-width: 100%;
    max-height: calc(100vh - 200px);
    object-fit: contain;
    border-radius: 8px;
  }

  .label {
    position: absolute;
    bottom: 0.5rem;
    left: 50%;
    transform: translateX(-50%);
    padding: 0.25rem 0.75rem;
    background: rgba(0, 0, 0, 0.6);
    border-radius: 4px;
    color: white;
    font-size: 0.75rem;
  }
}

.no-result {
  text-align: center;
  color: var(--text-muted);

  i {
    font-size: 3rem;
    margin-bottom: 1rem;
  }
}

// 設定表單
.settings-form {
  color: var(--text-primary);
}

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

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;

  label {
    font-size: 0.85rem;
    color: var(--text-secondary);
  }
}

.scale-options {
  display: flex;
  gap: 0.5rem;
}

.scale-btn {
  flex: 1;
  padding: 0.5rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
  }

  &.active {
    background: rgba(96, 165, 250, 0.2);
    border-color: var(--color-accent);
    color: var(--color-accent);
  }
}

.execute-btn {
  width: 100%;
  padding: 0.75rem 1rem;
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-hover) 100%);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-top: 0.5rem;

  &:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(124, 111, 173, 0.4);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.text-muted {
  color: var(--text-muted);
}
</style>
