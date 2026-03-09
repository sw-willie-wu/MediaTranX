<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useSettingsStore } from '@/stores/settings'
import { useToast } from '@/composables/useToast'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import { apiFetch, getApiBase } from '@/composables/useApi'

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

const emit = defineEmits<{
  (e: 'submit', taskId: string): void
  (e: 'complete', taskId: string): void
}>()

const filesStore = useFilesStore()
const taskStore = useTaskStore()
const settings = useSettingsStore()
const toast = useToast()

const isLoading = ref(false)
const isInstalling = ref(false)
const error = ref<string | null>(null)

// ========== Whisper 模型狀態 ==========
const whisperAvailable = ref<boolean | null>(null)
const whisperDownloadedMap = ref<Record<string, boolean | null>>({})

const baseModelSizes = [
  { value: 'tiny',     label: 'Tiny (~75 MB)',    desc: '最快，精度較低' },
  { value: 'base',     label: 'Base (~145 MB)',   desc: '快速' },
  { value: 'small',    label: 'Small (~484 MB)',  desc: '平衡' },
  { value: 'medium',   label: 'Medium (~1.5 GB)', desc: '推薦' },
  { value: 'large-v3', label: 'Large-v3 (~3 GB)', desc: '最佳精度' },
]

const modelSizesWithBadge = computed(() =>
  baseModelSizes.map(m => {
    const dl = whisperDownloadedMap.value[m.value]
    return { ...m, badge: dl === undefined ? null : dl ? 'ok' as const : 'err' as const }
  })
)

async function loadAllWhisperStatus() {
  await Promise.allSettled(baseModelSizes.map(async ({ value: size }) => {
    try {
      const res = await fetch(`${getApiBase()}/video/whisper/status?model_size=${size}`)
      if (!res.ok) return
      const data = await res.json()
      whisperDownloadedMap.value[size] = data.model_downloaded
      if (whisperAvailable.value === null) whisperAvailable.value = data.available
    } catch {}
  }))
}

// ========== 翻譯模型（從後端 registry 取得） ==========
interface TranslateModelItem {
  key: string
  label: string
  desc: string
  sizeMb: number
  downloaded: boolean
}

const selectedTranslateModel = ref('translategemma:4b:Q4_K_M')
const translateEnvAvailable = ref<boolean | null>(null)
const translateModelsFromApi = ref<TranslateModelItem[]>([])

const translateModelOptions = computed(() =>
  translateModelsFromApi.value.map(m => ({
    value: m.key,
    label: m.label,
    desc: m.desc,
    badge: m.downloaded ? 'ok' as const : 'err' as const,
  }))
)

async function loadTranslateModels() {
  try {
    const [statusRes, modelsRes] = await Promise.all([
      apiFetch('/setup/status'),
      apiFetch('/setup/models'),
    ])
    if (statusRes.ok) {
      const s = await statusRes.json()
      translateEnvAvailable.value = s.ai_env_ready ?? null
    }
    if (!modelsRes.ok) return
    const data = await modelsRes.json()
    translateModelsFromApi.value = (data.models as any[])
      .filter((m: any) => m.category === 'translate')
      .sort((a: any, b: any) => a.size_mb - b.size_mb)
      .map((m: any) => {
        const dashIdx = m.variant.indexOf('-')
        const size = m.variant.slice(0, dashIdx)
        const quant = m.variant.slice(dashIdx + 1)
        const sizeGb = (m.size_mb / 1024).toFixed(1)
        const desc = m.description ? `${sizeGb} GB · ${m.description}` : `${sizeGb} GB`
        return {
          key: `${m.family}:${size}:${quant}`,
          label: m.label,
          desc,
          sizeMb: m.size_mb,
          downloaded: m.downloaded,
        }
      })
  } catch {}
}

// ========== 字幕選項 ==========
const language = ref('')
const modelSize = ref('medium')
const outputFormat = ref('srt')
const outputPath = ref('')

// ========== 翻譯選項 ==========
const enableTranslation = ref(false)
const targetLanguage = ref('zh-TW')
const keepNames = ref(true)
const translateStyle = ref('colloquial')
const glossaryText = ref('')

const translateLanguages = ref<{ code: string; name: string }[]>([
  { code: 'zh-TW', name: '繁體中文' },
  { code: 'zh-CN', name: '簡體中文' },
  { code: 'en', name: '英文' },
  { code: 'ja', name: '日文' },
  { code: 'ko', name: '韓文' },
])

// ========== 進階分句選項 ==========
const showAdvanced = ref(false)
const wordTimestamps = ref(false)
const conditionOnPreviousText = ref(true)
const minSilenceDurationMs = ref(200)
const vadThreshold = ref(0.3)

// ========== 語言 / 格式選項 ==========
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

const outputFormats = [
  { value: 'srt', label: 'SRT' },
  { value: 'vtt', label: 'VTT (WebVTT)' },
]

const translateStyles = [
  { value: 'colloquial', label: '口語化' },
  { value: 'formal', label: '正式' },
  { value: 'literal', label: '直譯' },
]

const targetLanguageOptions = computed(() =>
  translateLanguages.value.map(l => ({ value: l.code, label: l.name }))
)

// ========== localStorage 持久化 ==========
const STORAGE_KEY = 'translate-preferences'

function savePreferences() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    translateModel: selectedTranslateModel.value,
  }))
}

function loadPreferences(): string | null {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (!saved) return null
  try {
    const parsed = JSON.parse(saved)
    // 新格式
    if (parsed.translateModel) return parsed.translateModel
    // 舊格式向下相容
    if (parsed.modelType && parsed.modelSize && parsed.quantization) {
      return `${parsed.modelType}:${parsed.modelSize}:${parsed.quantization}`
    }
  } catch {}
  return null
}

// ========== VRAM 自動推薦 ==========
async function autoRecommend() {
  await settings.loadDeviceInfo()
  const totalBytes = settings.deviceInfo?.memory_total
  if (!totalBytes) return

  const usableMb = totalBytes / (1024 * 1024) - 1500

  const sorted = [...translateModelsFromApi.value].sort((a, b) => b.sizeMb - a.sizeMb)
  const best = sorted.find(m => m.sizeMb <= usableMb)
  if (best) selectedTranslateModel.value = best.key
}

// ========== Glossary 解析 ==========
function parseGlossary(): Record<string, string> | undefined {
  const text = glossaryText.value.trim()
  if (!text) return undefined
  const dict: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
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

// ========== 輸出路徑 ==========
const sourceBaseName = computed(() => {
  const file = filesStore.currentFile
  if (!file?.originalName) return 'output'
  const name = file.originalName
  const lastDot = name.lastIndexOf('.')
  return lastDot > 0 ? name.substring(0, lastDot) : name
})

const defaultOutputName = computed(() => `${sourceBaseName.value}.${outputFormat.value}`)

const displayOutputPath = computed(() => {
  if (outputPath.value) {
    const parts = outputPath.value.replace(/\\/g, '/').split('/')
    return parts[parts.length - 1]
  }
  return defaultOutputName.value
})

// ========== 安裝 AI 推理環境 ==========
async function installTranslate() {
  isInstalling.value = true
  error.value = null

  try {
    const response = await apiFetch('/setup/initialize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || '安裝失敗')
    }

    const result = await response.json()

    taskStore.addTask({
      taskId: result.task_id,
      taskType: 'setup/initialize',
      status: 'pending',
      progress: 0,
      message: null,
      result: null,
      error: null,
      createdAt: new Date(),
      updatedAt: new Date(),
      label: '安裝 AI 推理環境',
    })
    toast.show('開始安裝 AI 推理環境，請稍候...', { type: 'info', icon: 'bi-download' })

    const checkDone = setInterval(async () => {
      const task = taskStore.tasks.get(result.task_id)
      if (task && (task.status === 'completed' || task.status === 'failed')) {
        clearInterval(checkDone)
        isInstalling.value = false
        if (task.status === 'completed') {
          toast.show('AI 推理環境安裝完成', { type: 'success' })
          await loadTranslateModels()
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

// ========== 提交字幕生成 ==========
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

    if (language.value) body.language = language.value

    if (enableTranslation.value && targetLanguage.value) {
      const [tmType, tmSize, tmQuant] = selectedTranslateModel.value.split(':')
      body.target_language = targetLanguage.value
      body.translate_model_type = tmType
      body.translate_model_size = tmSize
      body.translate_quantization = tmQuant
      body.keep_names = keepNames.value
      body.translate_style = translateStyle.value
      const glossary = parseGlossary()
      if (glossary) body.glossary = glossary
    }

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

    const response = await apiFetch('/video/subtitle/generate', {
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

// ========== 選擇輸出檔案 ==========
async function selectOutputFile() {
  if (window.electron?.saveFileDialog) {
    const result = await window.electron.saveFileDialog({
      title: '選擇輸出位置',
      defaultPath: defaultOutputName.value,
      filters: [{ name: '字幕檔案', extensions: [outputFormat.value] }],
    })
    if (result) outputPath.value = result
  }
}

// ========== 載入翻譯語言 ==========
async function loadTranslateLanguages(retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      const response = await apiFetch('/video/translategemma/languages')
      if (response.ok) {
        translateLanguages.value = await response.json()
        return
      }
    } catch {}
    if (i < retries - 1) await new Promise(r => setTimeout(r, 1000))
  }
}

// ========== Watchers ==========
watch(() => props.fileId, () => { outputPath.value = '' })

watch(outputFormat, () => { outputPath.value = '' })

watch(enableTranslation, (val) => {
  if (val) loadTranslateLanguages()
})

watch(selectedTranslateModel, savePreferences)

// ========== Expose ==========
const isDisabled = computed(() =>
  isLoading.value || !props.fileId || whisperAvailable.value === false
)

defineExpose({ submitGenerate, isLoading, isDisabled })

// ========== 初始化 ==========
onMounted(async () => {
  loadAllWhisperStatus()
  loadTranslateModels()
  settings.loadDeviceInfo()

  const saved = loadPreferences()
  if (saved) {
    selectedTranslateModel.value = saved
  } else {
    await autoRecommend()
  }
})
</script>

<template>
  <div class="subtitle-panel">
    <div v-if="error" class="error-msg">{{ error }}</div>

    <div class="form-group">
      <label>語言</label>
      <AppSelect v-model="language" :options="languages" size="sm" />
    </div>

    <div class="form-group">
      <label>模型設定</label>
      <AppSelect v-model="modelSize" :options="modelSizesWithBadge" size="sm" />
    </div>

    <!-- 進階分句設定 -->
    <div class="form-group">
      <AppToggle v-model="showAdvanced">
        進階分句設定 <span class="label-hint">（適合多人對話）</span>
      </AppToggle>

      <div v-if="showAdvanced" class="advanced-options">
        <div class="option-row">
          <AppToggle
            :modelValue="!conditionOnPreviousText"
            @update:modelValue="v => conditionOnPreviousText = !v"
          >獨立辨識每段語音</AppToggle>
          <span class="option-hint">關閉上下文關聯，避免句子合併</span>
        </div>

        <div class="option-row">
          <AppToggle v-model="wordTimestamps">詞級時間戳</AppToggle>
          <span class="option-hint">更精確的分句邊界</span>
        </div>

        <div class="option-row slider-row">
          <label>最小靜音時長</label>
          <div class="slider-group">
            <input type="range" v-model.number="minSilenceDurationMs" min="100" max="2000" step="100" />
            <span class="slider-value">{{ minSilenceDurationMs }} ms</span>
          </div>
          <span class="option-hint">停頓超過此時長會分句（預設 200ms）</span>
        </div>

        <div class="option-row slider-row">
          <label>VAD 敏感度</label>
          <div class="slider-group">
            <input type="range" v-model.number="vadThreshold" min="0.1" max="0.9" step="0.1" />
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
      <AppToggle v-model="enableTranslation">翻譯字幕</AppToggle>

      <div v-if="enableTranslation" class="translate-options">
        <!-- 未安裝 -->
        <div v-if="translateEnvAvailable === false" class="install-prompt">
          <p class="install-hint">翻譯功能需要 AI 推理環境，首次使用前請先安裝</p>
          <button class="install-btn" :disabled="isInstalling" @click="installTranslate">
            <span v-if="isInstalling" class="spinner-border spinner-border-sm me-2"></span>
            <i v-else class="bi bi-download me-1"></i>
            {{ isInstalling ? '安裝中...' : '安裝 AI 推理環境' }}
          </button>
        </div>

        <!-- 已安裝 -->
        <template v-else>
          <div class="form-group">
            <label>目標語言</label>
            <AppSelect v-model="targetLanguage" :options="targetLanguageOptions" size="sm" />
          </div>

          <div class="form-group">
            <label>翻譯模型</label>
            <AppSelect v-model="selectedTranslateModel" :options="translateModelOptions" size="sm" />
          </div>

          <div class="form-group">
            <label>翻譯風格</label>
            <AppSelect v-model="translateStyle" :options="translateStyles" size="sm" />
          </div>

          <div class="option-row">
            <AppToggle v-model="keepNames">保留人名和專有名詞原文</AppToggle>
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

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;

  label {
    font-size: 0.85rem;
    color: var(--text-secondary);
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

      &:hover { transform: scale(1.1); }
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
