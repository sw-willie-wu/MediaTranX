<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import ToolLayout from '@/components/ToolLayout.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'

// 子功能列表
const subFunctions = [
  { id: 'translate', name: '翻譯', icon: 'bi-translate' },
  { id: 'pdf-convert', name: 'PDF 轉換', icon: 'bi-file-earmark-pdf-fill' },
  { id: 'ocr', name: '文字辨識', icon: 'bi-type' },
  { id: 'merge', name: '合併文件', icon: 'bi-union' },
  { id: 'split', name: '分割文件', icon: 'bi-layout-split' },
]

const currentFunction = ref('translate')

const filesStore = useFilesStore()
const taskStore = useTaskStore()
const toast = useToast()

// View 專屬狀態
const hasFile = ref(false)
const hasResult = ref(false)
const currentFileName = ref('')
const fileId = ref<string | null>(null)
const isUploading = ref(false)
const isSubmitting = ref(false)
const isInstalling = ref(false)
const error = ref<string | null>(null)

// 翻譯選項
const sourceLanguage = ref('en')
const targetLanguage = ref('zh-TW')
const translateModelSize = ref('4b')
const translateLanguages = ref<{ code: string; name: string }[]>([])
const translateStatus = ref<{
  available: boolean
  model_size: string
  model_downloaded: boolean
  device: string
  compute_type: string
  device_name: string
  missing_packages?: string[]
  gpu_upgrade?: boolean
} | null>(null)

// 翻譯模型大小選項（GGUF Q4_K_M 量化）
const translateModelSizes = [
  { value: '4b', label: '4B (~2.5 GB)', desc: '推薦' },
  { value: '12b', label: '12B (~7.3 GB)', desc: '較佳品質' },
  { value: '27b', label: '27B (~16.5 GB)', desc: '最佳品質' },
]

// 語言選項（從 API 載入）
const languageOptions = computed(() =>
  translateLanguages.value.map(l => ({ value: l.code, label: l.name }))
)

function selectFunction(id: string) {
  currentFunction.value = id
}

function handleExport() {
  console.log('Export document')
}

async function handleFile(file: File, srcDir?: string) {
  hasFile.value = true
  currentFileName.value = file.name
  isUploading.value = true
  error.value = null

  try {
    const id = await filesStore.uploadFile(file, srcDir)
    fileId.value = id
  } catch (e) {
    error.value = e instanceof Error ? e.message : '上傳失敗'
    fileId.value = null
  } finally {
    isUploading.value = false
  }
}

// 載入翻譯語言列表
async function loadTranslateLanguages() {
  try {
    const response = await fetch('/api/document/translategemma/languages')
    if (response.ok) {
      translateLanguages.value = await response.json()
    }
  } catch (e) {
    console.error('Failed to load translate languages:', e)
  }
}

// 載入翻譯模型狀態
async function loadTranslateStatus() {
  try {
    const response = await fetch(`/api/document/translategemma/status?model_size=${translateModelSize.value}`)
    if (response.ok) {
      translateStatus.value = await response.json()
    }
  } catch (e) {
    console.error('Failed to load translate status:', e)
  }
}

// 安裝翻譯功能
async function installTranslate() {
  isInstalling.value = true
  error.value = null

  try {
    const response = await fetch('/api/setup/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feature: 'translategemma' }),
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || '安裝失敗')
    }

    const result = await response.json()

    if (!result.task_id) {
      toast.show('翻譯功能已就緒', { type: 'success' })
      await loadTranslateStatus()
      return
    }

    taskStore.addTask({
      taskId: result.task_id,
      taskType: 'setup/install',
      status: 'pending',
      progress: 0,
      message: null,
      result: null,
      error: null,
      createdAt: new Date(),
      updatedAt: new Date(),
      label: '安裝翻譯功能',
    })
    toast.show('開始安裝翻譯功能，請稍候...', { type: 'info', icon: 'bi-download' })

    const checkDone = setInterval(async () => {
      const task = taskStore.tasks.get(result.task_id)
      if (task && (task.status === 'completed' || task.status === 'failed')) {
        clearInterval(checkDone)
        isInstalling.value = false
        if (task.status === 'completed') {
          toast.show('翻譯功能安裝完成', { type: 'success' })
          await loadTranslateStatus()
        } else {
          error.value = '安裝失敗，請查看任務列表'
        }
      }
    }, 2000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '安裝失敗'
    isInstalling.value = false
  }
}

// 提交翻譯
async function submitTranslate() {
  if (!fileId.value) return

  isSubmitting.value = true
  error.value = null

  try {
    const response = await fetch('/api/document/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_id: fileId.value,
        source_language: sourceLanguage.value,
        target_language: targetLanguage.value,
        model_size: translateModelSize.value,
      }),
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || '翻譯提交失敗')
    }

    const result = await response.json()
    taskStore.addTask({
      taskId: result.task_id,
      taskType: 'document/translate',
      status: 'pending',
      progress: 0,
      message: null,
      result: null,
      error: null,
      createdAt: new Date(),
      updatedAt: new Date(),
      label: '文件翻譯',
      fileName: currentFileName.value,
    })
    toast.show('開始文件翻譯', { type: 'info', icon: 'bi-translate' })
  } catch (e) {
    error.value = e instanceof Error ? e.message : '發生錯誤'
  } finally {
    isSubmitting.value = false
  }
}

onMounted(() => {
  loadTranslateLanguages()
  loadTranslateStatus()
})
</script>

<template>
  <ToolLayout
    title="文件工具"
    accept-type="document"
    upload-icon="bi-file-earmark-text-fill"
    upload-label="拖曳文件到這裡"
    upload-accept=".pdf,.doc,.docx,.txt,.srt,.vtt,.md,.csv,.json"
    :sub-functions="subFunctions"
    :current-function="currentFunction"
    :has-result="hasResult"
    @select-function="selectFunction"
    @export="handleExport"
    @file="handleFile"
  >
    <!-- 預覽區域 -->
    <template #preview="{ file, previewUrl, mode }">
      <div class="preview-display">
        <div class="document-preview">
          <i class="bi bi-file-earmark-text-fill"></i>
          <p class="filename">{{ file.name }}</p>
          <p v-if="isUploading" class="upload-hint">上傳中...</p>
        </div>
      </div>
    </template>

    <!-- 設定面板 -->
    <template #settings>
      <div class="settings-form">
        <!-- 翻譯 -->
        <div v-if="currentFunction === 'translate'" class="function-settings">
          <h6 class="settings-title">
            <i class="bi bi-translate me-2"></i>翻譯
          </h6>

          <div v-if="error" class="error-msg">{{ error }}</div>

          <!-- 未安裝或需升級：顯示安裝按鈕 -->
          <div v-if="translateStatus && !translateStatus.available" class="install-prompt">
            <p class="install-hint">
              {{ translateStatus.gpu_upgrade
                ? '偵測到 GPU，建議安裝 GPU 版以大幅加速翻譯'
                : '翻譯功能需要額外元件，首次使用前請先安裝' }}
            </p>
            <button
              class="install-btn"
              :disabled="isInstalling"
              @click="installTranslate"
            >
              <span v-if="isInstalling" class="spinner-border spinner-border-sm me-2"></span>
              <i v-else class="bi me-1" :class="translateStatus.gpu_upgrade ? 'bi-gpu-card' : 'bi-download'"></i>
              {{ isInstalling ? '安裝中...' : (translateStatus.gpu_upgrade ? '安裝 GPU 版' : '安裝翻譯功能') }}
            </button>
          </div>

          <!-- 已安裝：顯示設定 -->
          <template v-else-if="!translateStatus || translateStatus.available">
            <div class="form-group">
              <label>來源語言</label>
              <AppSelect
                v-model="sourceLanguage"
                :options="languageOptions"
                size="sm"
              />
            </div>

            <div class="form-group">
              <label>目標語言</label>
              <AppSelect
                v-model="targetLanguage"
                :options="languageOptions"
                size="sm"
              />
            </div>

            <div class="form-group">
              <label>翻譯模型</label>
              <AppSelect
                v-model="translateModelSize"
                :options="translateModelSizes"
                size="sm"
              />
              <div v-if="translateStatus" class="model-status">
                <span class="status-item">
                  <i class="bi bi-check-circle-fill status-ok"></i>
                  翻譯功能已就緒
                  <span v-if="!translateStatus.model_downloaded" class="model-hint">(首次使用自動下載模型)</span>
                </span>
                <span class="status-item">
                  <i class="bi bi-gpu-card"></i>
                  {{ translateStatus.device_name }}
                </span>
              </div>
            </div>

            <button
              class="execute-btn"
              :disabled="isSubmitting || !fileId || isUploading"
              @click="submitTranslate"
            >
              <span v-if="isSubmitting" class="spinner-border spinner-border-sm me-2"></span>
              開始翻譯
            </button>
          </template>
        </div>

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

.error-msg {
  padding: 0.75rem;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 6px;
  color: #ef4444;
  font-size: 0.85rem;
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

.model-status {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 1rem;
  padding: 0.5rem 0.75rem;
  background: var(--input-bg);
  border-radius: 6px;
  font-size: 0.8rem;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  color: var(--text-secondary);

  i { font-size: 0.75rem; }
}

.status-ok { color: #10b981 !important; }
.status-err { color: #ef4444 !important; }

.model-hint {
  color: var(--text-muted);
  font-size: 0.75rem;
}

.install-prompt {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0;
  text-align: center;
}

.install-hint {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin: 0;
}

.install-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  padding: 0.6rem 1rem;
  background: linear-gradient(135deg, var(--color-info) 0%, var(--color-primary) 100%);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(96, 165, 250, 0.3);
  }

  &:disabled {
    opacity: 0.7;
    cursor: not-allowed;
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

.text-muted { color: var(--text-muted); }
</style>
