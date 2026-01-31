<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useFilesStore } from '@/stores/files'
import { useProgress } from '@/composables/useProgress'
import ProgressBar from '@/components/common/ProgressBar.vue'
import AppSelect from '@/components/common/AppSelect.vue'

// Props
const props = defineProps<{
  fileId: string | null
  mediaInfo: {
    duration: number
    width: number
    height: number
    fps: number
    video_codec: string
    audio_codec: string
    bitrate: number
    file_size: number
  } | null
}>()

// Emits
const emit = defineEmits<{
  (e: 'submit', taskId: string): void
  (e: 'complete', taskId: string): void
}>()

const filesStore = useFilesStore()

// 進度追蹤
const { progress, message, subscribe, reset } = useProgress({
  onComplete: (taskId) => {
    isProcessing.value = false
    emit('complete', taskId)
  },
  onError: (taskId, err) => {
    isProcessing.value = false
    error.value = err
  }
})

// 狀態
const isLoading = ref(false)
const isProcessing = ref(false)
const currentTaskId = ref<string | null>(null)
const error = ref<string | null>(null)

// Whisper 模型狀態
const whisperStatus = ref<{
  available: boolean
  model_size: string
  model_downloaded: boolean
  device: string
  compute_type: string
  device_name: string
} | null>(null)

// 字幕選項
const language = ref('')
const modelSize = ref('medium')
const outputFormat = ref('srt')
const outputPath = ref('')

// 語言選項
const languages = [
  { value: '', label: '自動偵測' },
  { value: 'zh', label: '中文' },
  { value: 'en', label: '英文' },
  { value: 'ja', label: '日文' },
  { value: 'ko', label: '韓文' },
  { value: 'fr', label: '法文' },
  { value: 'de', label: '德文' },
  { value: 'es', label: '西班牙文' },
  { value: 'ru', label: '俄文' },
  { value: 'pt', label: '葡萄牙文' },
  { value: 'it', label: '義大利文' },
  { value: 'th', label: '泰文' },
  { value: 'vi', label: '越南文' },
]

// 模型大小選項
const modelSizes = [
  { value: 'tiny', label: 'Tiny (~75 MB)', desc: '最快，精度較低' },
  { value: 'base', label: 'Base (~145 MB)', desc: '快速' },
  { value: 'small', label: 'Small (~484 MB)', desc: '平衡' },
  { value: 'medium', label: 'Medium (~1.5 GB)', desc: '推薦' },
  { value: 'large-v3', label: 'Large-v3 (~3 GB)', desc: '最佳精度' },
]

// 輸出格式選項
const outputFormats = [
  { value: 'srt', label: 'SRT' },
  { value: 'vtt', label: 'VTT (WebVTT)' },
]

// 取得來源檔名（不含副檔名）
const sourceBaseName = computed(() => {
  const file = filesStore.currentFile
  if (!file?.originalName) return 'output'
  const name = file.originalName
  const lastDot = name.lastIndexOf('.')
  return lastDot > 0 ? name.substring(0, lastDot) : name
})

// 預設輸出檔名
const defaultOutputName = computed(() => {
  return `${sourceBaseName.value}.${outputFormat.value}`
})

// 顯示的輸出路徑
const displayOutputPath = computed(() => {
  if (outputPath.value) {
    const parts = outputPath.value.replace(/\\/g, '/').split('/')
    return parts[parts.length - 1]
  }
  return defaultOutputName.value
})

// 載入 Whisper 模型狀態
async function loadWhisperStatus() {
  try {
    const response = await fetch(`/api/video/whisper/status?model_size=${modelSize.value}`)
    if (response.ok) {
      whisperStatus.value = await response.json()
    }
  } catch (e) {
    console.error('Failed to load whisper status:', e)
  }
}

// 提交字幕生成
async function submitGenerate() {
  if (!props.fileId) return

  isLoading.value = true
  error.value = null

  try {
    const body: Record<string, any> = {
      file_id: props.fileId,
      model_size: modelSize.value,
      output_format: outputFormat.value,
    }

    if (language.value) {
      body.language = language.value
    }

    if (outputPath.value) {
      const path = outputPath.value.replace(/\\/g, '/')
      const lastSlash = path.lastIndexOf('/')
      if (lastSlash > 0) {
        body.output_dir = path.substring(0, lastSlash)
        body.output_filename = path.substring(lastSlash + 1)
      } else {
        body.output_filename = path
      }
    }

    const response = await fetch('/api/video/subtitle/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || '字幕生成失敗')
    }

    const result = await response.json()
    currentTaskId.value = result.task_id
    isProcessing.value = true
    reset()
    subscribe(result.task_id)
    emit('submit', result.task_id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '發生錯誤'
  } finally {
    isLoading.value = false
  }
}

// 選擇輸出檔案
async function selectOutputFile() {
  if (window.electron?.saveFileDialog) {
    const ext = outputFormat.value
    const filters = [
      { name: '字幕檔案', extensions: [ext] }
    ]
    const result = await window.electron.saveFileDialog({
      title: '選擇輸出位置',
      defaultPath: defaultOutputName.value,
      filters
    })
    if (result) {
      outputPath.value = result
    }
  }
}

// 監聽 fileId 變化
watch(() => props.fileId, () => {
  outputPath.value = ''
})

// 模型大小變更時更新狀態
watch(modelSize, () => {
  loadWhisperStatus()
})

// 格式變更時重置輸出路徑
watch(outputFormat, () => {
  outputPath.value = ''
})

// 初始化時載入 whisper 狀態
onMounted(() => {
  loadWhisperStatus()
})
</script>

<template>
  <div class="subtitle-panel">
    <!-- 錯誤訊息 -->
    <div v-if="error && !isProcessing" class="error-msg">
      {{ error }}
    </div>

    <div class="form-group">
      <label>語言</label>
      <AppSelect v-model="language" :options="languages" size="sm" />
    </div>

    <div class="form-group">
      <label>模型設定</label>
      <AppSelect v-model="modelSize" :options="modelSizes" size="sm" />
      <div v-if="whisperStatus" class="model-status">
        <span class="status-item">
          <i class="bi" :class="whisperStatus.available ? 'bi-check-circle-fill status-ok' : 'bi-x-circle-fill status-err'"></i>
          {{ whisperStatus.available ? 'Whisper 可用' : 'Whisper 未安裝' }}
          <span v-if="whisperStatus.available && !whisperStatus.model_downloaded" class="model-hint">(首次使用自動下載)</span>
        </span>
        <span class="status-item">
          <i class="bi bi-gpu-card"></i>
          {{ whisperStatus.device_name }}
        </span>
      </div>
    </div>

    <div class="form-group">
      <label>輸出格式</label>
      <AppSelect v-model="outputFormat" :options="outputFormats" size="sm" />
    </div>

    <div class="form-group">
      <label>輸出檔案</label>
      <div class="file-select" @click="selectOutputFile">
        <span class="file-path">{{ displayOutputPath }}</span>
        <i class="bi bi-folder2-open"></i>
      </div>
    </div>

    <!-- 生成進度 -->
    <div v-if="isProcessing">
      <ProgressBar :progress="progress" :message="message" :show-percentage="true" />
    </div>

    <button
      class="execute-btn"
      :disabled="isLoading || isProcessing || !fileId || (whisperStatus && !whisperStatus.available)"
      @click="submitGenerate"
    >
      <span v-if="isProcessing" class="spinner-border spinner-border-sm me-2"></span>
      {{ isProcessing ? '提取中...' : '開始提取字幕' }}
    </button>
  </div>
</template>

<style lang="scss" scoped>
.subtitle-panel {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.error-msg {
  padding: 0.75rem;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 6px;
  color: #ef4444;
  font-size: 0.85rem;
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

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;

  label {
    font-size: 0.85rem;
    color: var(--text-secondary);
  }
}

.file-select {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 6px;
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: var(--input-bg-focus);
    border-color: var(--input-border-focus);
  }

  .file-path {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    margin-right: 0.5rem;
  }

  i { color: var(--text-muted); }
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
</style>
