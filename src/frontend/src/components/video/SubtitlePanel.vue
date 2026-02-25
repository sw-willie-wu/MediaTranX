<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useSettingsStore } from '@/stores/settings'
import { useToast } from '@/composables/useToast'
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
const taskStore = useTaskStore()
const settings = useSettingsStore()
const toast = useToast()

// 狀態
const isLoading = ref(false)
const isInstalling = ref(false)
const error = ref<string | null>(null)

// Whisper 模型狀態
const whisperStatus = ref<{
  available: boolean
  model_size: string
  model_downloaded: boolean
} | null>(null)

// 翻譯模型狀態
const translateStatus = ref<{
  available: boolean
  model_size: string
  model_downloaded: boolean
} | null>(null)

// 字幕選項
const language = ref('')
const modelSize = ref('medium')
const outputFormat = ref('srt')
const outputPath = ref('')

// 翻譯選項
const enableTranslation = ref(false)
const targetLanguage = ref('zh-TW')
const translateModelType = ref<'translategemma' | 'qwen3'>('translategemma')
const translateModelSize = ref('4b')
const translateQuantization = ref('Q4_K_M')
const showAdvancedTranslate = ref(false)

// 預設語言列表（避免 API 載入前顯示空白）
const translateLanguages = ref<{ code: string; name: string }[]>([
  { code: 'zh-TW', name: '繁體中文' },
  { code: 'zh-CN', name: '簡體中文' },
  { code: 'en', name: '英文' },
  { code: 'ja', name: '日文' },
  { code: 'ko', name: '韓文' },
])
const keepNames = ref(true)
const translateStyle = ref('colloquial')
const glossaryText = ref('')

// 進階分句選項
const showAdvanced = ref(false)
const wordTimestamps = ref(false)
const conditionOnPreviousText = ref(true)
const minSilenceDurationMs = ref(200)
const vadThreshold = ref(0.3)

// 量化選項靜態配置
const quantOptions: Record<string, Record<string, Array<{value: string, label: string, sizeMb: number}>>> = {
  translategemma: {
    '4b':  [{ value: 'Q4_K_M', label: 'Q4_K_M (2.5 GB)', sizeMb: 2500 }],
    '12b': [
      { value: 'Q4_K_M', label: 'Q4_K_M (7.3 GB)', sizeMb: 7300 },
      { value: 'Q4_K_S', label: 'Q4_K_S (6.9 GB)', sizeMb: 6940 },
      { value: 'Q3_K_L', label: 'Q3_K_L (6.5 GB)', sizeMb: 6480 },
      { value: 'Q3_K_M', label: 'Q3_K_M (6.0 GB)', sizeMb: 6010 },
      { value: 'Q3_K_S', label: 'Q3_K_S (5.5 GB)', sizeMb: 5460 },
    ],
    '27b': [{ value: 'Q4_K_M', label: 'Q4_K_M (16.5 GB)', sizeMb: 16500 }],
  },
  qwen3: {
    '1.7b': [{ value: 'Q8_0', label: 'Q8_0 (1.83 GB)', sizeMb: 1830 }],
    '4b':   [{ value: 'Q4_K_M', label: 'Q4_K_M (2.5 GB)', sizeMb: 2500 }],
    '8b':   [{ value: 'Q4_K_M', label: 'Q4_K_M (5 GB)', sizeMb: 5030 }],
    '14b':  [
      { value: 'Q4_K_M', label: 'Q4_K_M (9 GB)', sizeMb: 9000 },
      { value: 'Q4_K_S', label: 'Q4_K_S (8.6 GB)', sizeMb: 8570 },
      { value: 'Q3_K_M', label: 'Q3_K_M (7.3 GB)', sizeMb: 7320 },
      { value: 'Q3_K_S', label: 'Q3_K_S (6.7 GB)', sizeMb: 6660 },
    ],
  },
}

const availableQuants = computed(() =>
  quantOptions[translateModelType.value]?.[translateModelSize.value]
    ?? [{ value: 'Q4_K_M', label: 'Q4_K_M', sizeMb: 0 }]
)
const showQuantSelector = computed(() => availableQuants.value.length > 1)

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

// 翻譯模型類型選項
const translateModelTypes = [
  { value: 'translategemma', label: 'TranslateGemma', desc: '翻譯專用模型' },
  { value: 'qwen3', label: 'Qwen3', desc: '通用 LLM' },
]

// 翻譯模型大小選項（根據模型類型動態切換）
const translateGemmaSizes = [
  { value: '4b', label: '4B (~2.5 GB)', desc: '推薦' },
  { value: '12b', label: '12B (~7.3 GB)', desc: '較佳品質' },
  { value: '27b', label: '27B (~16.5 GB)', desc: '最佳品質' },
]
const qwen3Sizes = [
  { value: '1.7b', label: '1.7B (~1.83 GB)', desc: '輕量' },
  { value: '4b', label: '4B (~2.5 GB)', desc: '推薦' },
  { value: '8b', label: '8B (~5 GB)', desc: '較佳品質' },
  { value: '14b', label: '14B (~9 GB)', desc: '最佳品質' },
]

const translateModelSizes = computed(() =>
  translateModelType.value === 'qwen3' ? qwen3Sizes : translateGemmaSizes
)

// 翻譯風格選項
const translateStyles = [
  { value: 'colloquial', label: '口語化' },
  { value: 'formal', label: '正式' },
  { value: 'literal', label: '直譯' },
]

// 目標語言選項（從 API 載入）
const targetLanguageOptions = computed(() =>
  translateLanguages.value.map(l => ({ value: l.code, label: l.name }))
)

// === localStorage 持久化 ===
const STORAGE_KEY = 'translate-preferences'

function savePreferences() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    modelType: translateModelType.value,
    modelSize: translateModelSize.value,
    quantization: translateQuantization.value,
  }))
}

function loadPreferences(): { modelType: string; modelSize: string; quantization: string } | null {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (!saved) return null
  try { return JSON.parse(saved) } catch { return null }
}

// === 首次啟動 VRAM 推薦 ===
async function autoRecommend() {
  await settings.loadDeviceInfo()
  const totalBytes = settings.deviceInfo?.memory_total
  if (!totalBytes) return

  const usableMb = totalBytes / (1024 * 1024) - 1500  // 預留 OS + Whisper

  // 按品質降序排列（越大越好）
  const allModels = [
    { type: 'qwen3' as const, size: '14b', quant: 'Q4_K_M', mb: 9000 },
    { type: 'qwen3' as const, size: '14b', quant: 'Q4_K_S', mb: 8570 },
    { type: 'translategemma' as const, size: '12b', quant: 'Q4_K_M', mb: 7300 },
    { type: 'qwen3' as const, size: '14b', quant: 'Q3_K_M', mb: 7320 },
    { type: 'translategemma' as const, size: '12b', quant: 'Q4_K_S', mb: 6940 },
    { type: 'translategemma' as const, size: '12b', quant: 'Q3_K_L', mb: 6480 },
    { type: 'translategemma' as const, size: '12b', quant: 'Q3_K_M', mb: 6010 },
    { type: 'qwen3' as const, size: '14b', quant: 'Q3_K_S', mb: 6660 },
    { type: 'translategemma' as const, size: '12b', quant: 'Q3_K_S', mb: 5460 },
    { type: 'qwen3' as const, size: '8b', quant: 'Q4_K_M', mb: 5030 },
    { type: 'qwen3' as const, size: '4b', quant: 'Q4_K_M', mb: 2500 },
    { type: 'translategemma' as const, size: '4b', quant: 'Q4_K_M', mb: 2500 },
    { type: 'qwen3' as const, size: '1.7b', quant: 'Q8_0', mb: 1830 },
  ]

  const best = allModels.find(m => m.mb <= usableMb)
  if (best) {
    translateModelType.value = best.type
    translateModelSize.value = best.size
    translateQuantization.value = best.quant
  }
}

// 解析 glossary 文字為 dict（每行格式：原文 → 譯文 或 原文 = 譯文）
function parseGlossary(): Record<string, string> | undefined {
  const text = glossaryText.value.trim()
  if (!text) return undefined
  const dict: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    // 支援 → 和 = 兩種分隔符
    const sep = trimmed.includes('→') ? '→' : '='
    const parts = trimmed.split(sep)
    if (parts.length >= 2) {
      const src = parts[0].trim()
      const tgt = parts.slice(1).join(sep).trim()
      if (src && tgt) dict[src] = tgt
    }
  }
  return Object.keys(dict).length > 0 ? dict : undefined
}

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

// 載入翻譯模型狀態
async function loadTranslateStatus() {
  try {
    const response = await fetch(`/api/video/translate/status?model_type=${translateModelType.value}&model_size=${translateModelSize.value}&quantization=${translateQuantization.value}`)
    if (response.ok) {
      translateStatus.value = await response.json()
    }
  } catch (e) {
    console.error('Failed to load translate status:', e)
  }
}

// 載入翻譯語言列表（含重試機制）
async function loadTranslateLanguages(retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      const response = await fetch('/api/video/translategemma/languages')
      if (response.ok) {
        translateLanguages.value = await response.json()
        return
      }
    } catch (e) {
      console.error(`Failed to load translate languages (attempt ${i + 1}):`, e)
    }
    // 等待後重試
    if (i < retries - 1) {
      await new Promise(r => setTimeout(r, 1000))
    }
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
      // 已經安裝好了
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

    // 輪詢等安裝完成
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

    if (enableTranslation.value && targetLanguage.value) {
      body.target_language = targetLanguage.value
      body.translate_model_type = translateModelType.value
      body.translate_model_size = translateModelSize.value
      body.translate_quantization = translateQuantization.value
      body.keep_names = keepNames.value
      body.translate_style = translateStyle.value
      const glossary = parseGlossary()
      if (glossary) body.glossary = glossary
    }

    // 進階分句參數
    body.word_timestamps = wordTimestamps.value
    body.condition_on_previous_text = conditionOnPreviousText.value
    body.min_silence_duration_ms = minSilenceDurationMs.value
    body.vad_threshold = vadThreshold.value

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
    const fileName = filesStore.currentFile?.originalName ?? undefined
    const label = enableTranslation.value ? '字幕提取 + 翻譯' : '字幕提取'
    taskStore.addTask({
      taskId: result.task_id,
      taskType: 'subtitle/generate',
      status: 'pending',
      progress: 0,
      message: null,
      result: null,
      error: null,
      createdAt: new Date(),
      updatedAt: new Date(),
      label,
      fileName,
    })
    toast.show(`開始${label}`, { type: 'info', icon: 'bi-badge-cc-fill' })
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

// 翻譯模型類型變更時重設大小和量化
watch(translateModelType, (val) => {
  translateModelSize.value = val === 'qwen3' ? '4b' : '4b'
  // 量化會由 translateModelSize watcher 重設
  if (enableTranslation.value) loadTranslateStatus()
})

// 翻譯模型大小變更時重設量化為該 size 的第一個選項
watch(translateModelSize, () => {
  const quants = quantOptions[translateModelType.value]?.[translateModelSize.value]
  if (quants && quants.length > 0) {
    translateQuantization.value = quants[0].value
  }
  if (enableTranslation.value) loadTranslateStatus()
})

// 量化變更時重新查狀態
watch(translateQuantization, () => {
  if (enableTranslation.value) loadTranslateStatus()
})

// 偏好設定持久化
watch([translateModelType, translateModelSize, translateQuantization], () => {
  savePreferences()
})

// 格式變更時重置輸出路徑
watch(outputFormat, () => {
  outputPath.value = ''
})

// 啟用翻譯時載入語言列表和狀態
watch(enableTranslation, (val) => {
  if (val) {
    loadTranslateLanguages()
    loadTranslateStatus()
  }
})

// 暴露給父組件
const isDisabled = computed(() =>
  isLoading.value || !props.fileId || (whisperStatus.value && !whisperStatus.value.available) || (enableTranslation.value && translateStatus.value && !translateStatus.value.available)
)

defineExpose({
  submitGenerate,
  isLoading,
  isDisabled,
})

// 初始化
onMounted(async () => {
  loadWhisperStatus()
  settings.loadDeviceInfo()

  // 先讀 localStorage，若無則 autoRecommend
  const saved = loadPreferences()
  if (saved) {
    translateModelType.value = saved.modelType as 'translategemma' | 'qwen3'
    translateModelSize.value = saved.modelSize
    translateQuantization.value = saved.quantization
  } else {
    await autoRecommend()
  }
})
</script>

<template>
  <div class="subtitle-panel">
    <!-- 錯誤訊息 -->
    <div v-if="error" class="error-msg">
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
          <i class="bi" :class="!whisperStatus.available ? 'bi-x-circle-fill status-err' : whisperStatus.model_downloaded ? 'bi-check-circle-fill status-ok' : 'bi-exclamation-circle-fill status-warn'"></i>
          {{ whisperStatus.available ? (whisperStatus.model_downloaded ? '模型已掛載' : '首次使用自動下載模型') : 'Whisper 未安裝' }}
        </span>
      </div>
    </div>

    <!-- 進階分句設定（Whisper 參數） -->
    <div class="form-group">
      <label class="checkbox-label" @click="showAdvanced = !showAdvanced">
        <span class="checkbox" :class="{ checked: showAdvanced }">
          <i v-if="showAdvanced" class="bi bi-check"></i>
        </span>
        進階分句設定
        <span class="label-hint">（適合多人對話）</span>
      </label>

      <div v-if="showAdvanced" class="advanced-options">
        <div class="option-row">
          <label class="checkbox-label" @click.stop="conditionOnPreviousText = !conditionOnPreviousText">
            <span class="checkbox" :class="{ checked: !conditionOnPreviousText }">
              <i v-if="!conditionOnPreviousText" class="bi bi-check"></i>
            </span>
            獨立辨識每段語音
          </label>
          <span class="option-hint">關閉上下文關聯，避免句子合併</span>
        </div>

        <div class="option-row">
          <label class="checkbox-label" @click.stop="wordTimestamps = !wordTimestamps">
            <span class="checkbox" :class="{ checked: wordTimestamps }">
              <i v-if="wordTimestamps" class="bi bi-check"></i>
            </span>
            詞級時間戳
          </label>
          <span class="option-hint">更精確的分句邊界</span>
        </div>

        <div class="option-row slider-row">
          <label>最小靜音時長</label>
          <div class="slider-group">
            <input
              type="range"
              v-model.number="minSilenceDurationMs"
              min="100"
              max="2000"
              step="100"
            />
            <span class="slider-value">{{ minSilenceDurationMs }} ms</span>
          </div>
          <span class="option-hint">停頓超過此時長會分句（預設 200ms）</span>
        </div>

        <div class="option-row slider-row">
          <label>VAD 敏感度</label>
          <div class="slider-group">
            <input
              type="range"
              v-model.number="vadThreshold"
              min="0.1"
              max="0.9"
              step="0.1"
            />
            <span class="slider-value">{{ vadThreshold.toFixed(1) }}</span>
          </div>
          <span class="option-hint">越低越敏感，更容易分句（預設 0.3）</span>
        </div>
      </div>
    </div>

    <div class="form-group">
      <label>輸出格式</label>
      <AppSelect v-model="outputFormat" :options="outputFormats" size="sm" />
    </div>

    <!-- 翻譯字幕 -->
    <div class="form-group">
      <label class="checkbox-label" @click="enableTranslation = !enableTranslation">
        <span class="checkbox" :class="{ checked: enableTranslation }">
          <i v-if="enableTranslation" class="bi bi-check"></i>
        </span>
        翻譯字幕
      </label>

      <div v-if="enableTranslation" class="translate-options">
        <!-- 未安裝：顯示安裝按鈕 -->
        <div v-if="translateStatus && !translateStatus.available" class="install-prompt">
          <p class="install-hint">翻譯功能需要額外元件，首次使用前請先安裝</p>
          <button
            class="install-btn"
            :disabled="isInstalling"
            @click="installTranslate"
          >
            <span v-if="isInstalling" class="spinner-border spinner-border-sm me-2"></span>
            <i v-else class="bi bi-download me-1"></i>
            {{ isInstalling ? '安裝中...' : '安裝翻譯功能' }}
          </button>
        </div>

        <!-- 已安裝：顯示設定 -->
        <template v-else>
          <div class="form-group">
            <label>目標語言</label>
            <AppSelect
              v-model="targetLanguage"
              :options="targetLanguageOptions"
              size="sm"
            />
          </div>

          <div class="form-group">
            <label>翻譯模型類型</label>
            <AppSelect
              v-model="translateModelType"
              :options="translateModelTypes"
              size="sm"
            />
          </div>

          <div class="form-group">
            <label>模型大小</label>
            <AppSelect
              v-model="translateModelSize"
              :options="translateModelSizes"
              size="sm"
            />
            <div v-if="translateStatus" class="model-status">
              <span class="status-item">
                <i class="bi" :class="translateStatus.model_downloaded ? 'bi-check-circle-fill status-ok' : 'bi-exclamation-circle-fill status-warn'"></i>
                {{ translateStatus.model_downloaded ? '模型已掛載' : '首次使用自動下載模型' }}
              </span>
            </div>
          </div>

          <!-- 進階模型設定（量化選項） -->
          <div v-if="showQuantSelector" class="form-group">
            <label class="collapsible-label" @click="showAdvancedTranslate = !showAdvancedTranslate">
              <i class="bi" :class="showAdvancedTranslate ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
              進階模型設定
            </label>
            <div v-if="showAdvancedTranslate" class="advanced-options">
              <div class="form-group">
                <label>量化精度</label>
                <AppSelect v-model="translateQuantization" :options="availableQuants" size="sm" />
                <span class="option-hint">較低精度節省 VRAM，品質略降</span>
              </div>
            </div>
          </div>

          <div class="form-group">
            <label>翻譯風格</label>
            <AppSelect
              v-model="translateStyle"
              :options="translateStyles"
              size="sm"
            />
          </div>

          <div class="option-row">
            <label class="checkbox-label" @click.stop="keepNames = !keepNames">
              <span class="checkbox" :class="{ checked: keepNames }">
                <i v-if="keepNames" class="bi bi-check"></i>
              </span>
              保留人名和專有名詞原文
            </label>
            <span class="option-hint">如：角色名、地名、作品名等不翻譯</span>
          </div>

          <div class="form-group">
            <label>專有名詞字典</label>
            <textarea
              v-model="glossaryText"
              class="glossary-input"
              rows="3"
              placeholder="每行一筆，格式：原文 → 譯文&#10;例如：&#10;アノン → Anon&#10;MyGO → MyGO"
            ></textarea>
            <span class="option-hint">指定特定詞彙的翻譯方式</span>
          </div>
        </template>
      </div>
    </div>

    <div class="form-group">
      <label>輸出檔案</label>
      <div class="file-select" @click="selectOutputFile">
        <span class="file-path">{{ displayOutputPath }}</span>
        <i class="bi bi-folder2-open"></i>
      </div>
    </div>

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
.status-warn { color: #f59e0b !important; }
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

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  user-select: none;
}

.checkbox {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border: 1.5px solid var(--input-border);
  border-radius: 4px;
  background: var(--input-bg);
  transition: all 0.15s ease;
  flex-shrink: 0;

  i {
    font-size: 0.75rem;
    color: white;
  }

  &.checked {
    background: var(--color-primary);
    border-color: var(--color-primary);
  }
}

.translate-options {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 0.75rem;
  background: var(--input-bg);
  border-radius: 8px;
  border: 1px solid var(--input-border);
}

.collapsible-label {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  cursor: pointer;
  user-select: none;

  i {
    font-size: 0.7rem;
    color: var(--text-muted);
    transition: transform 0.2s ease;
  }
}

.label-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
  font-weight: normal;
}

.advanced-options {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 0.75rem;
  background: var(--input-bg);
  border-radius: 8px;
  border: 1px solid var(--input-border);
}

.option-row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;

  &.slider-row {
    gap: 0.4rem;

    > label {
      font-size: 0.8rem;
      color: var(--text-secondary);
    }
  }
}

.option-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.slider-group {
  display: flex;
  align-items: center;
  gap: 0.75rem;

  input[type="range"] {
    flex: 1;
    height: 4px;
    -webkit-appearance: none;
    appearance: none;
    background: var(--input-border);
    border-radius: 2px;
    outline: none;

    &::-webkit-slider-thumb {
      -webkit-appearance: none;
      appearance: none;
      width: 14px;
      height: 14px;
      background: var(--color-primary);
      border-radius: 50%;
      cursor: pointer;
      transition: transform 0.15s ease;

      &:hover {
        transform: scale(1.1);
      }
    }
  }

  .slider-value {
    font-size: 0.8rem;
    color: var(--text-secondary);
    min-width: 50px;
    text-align: right;
  }
}

.glossary-input {
  width: 100%;
  padding: 0.5rem 0.75rem;
  font-size: 0.85rem;
  font-family: inherit;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 6px;
  color: var(--text-primary);
  resize: vertical;
  min-height: 60px;
  transition: border-color 0.15s ease;

  &:focus {
    outline: none;
    border-color: var(--color-primary);
  }

  &::placeholder {
    color: var(--text-muted);
    font-size: 0.8rem;
  }
}

.install-prompt {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
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

</style>
