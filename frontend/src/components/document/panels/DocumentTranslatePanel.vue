<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import AppSelect from '@/components/common/AppSelect.vue'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { apiFetch } from '@/composables/useApi'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useModelStore } from '@/stores/models'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const taskStore = useTaskStore()
const toast = useToast()
const { submitTask, isProcessing } = useSubmitTask()
const modelStore = useModelStore()

// ── 翻譯模型（從 modelStore 取得）────────────────────────────────────────

const selectedTranslateModel = ref('translategemma:4b:Q4_K_M')
const translateEnvAvailable  = ref<boolean | null>(null)
const isInstalling = ref(false)
const error = ref<string | null>(null)

const translateModelOptions = computed(() =>
  modelStore.byCategory('translate')
    .slice()
    .sort((a, b) => a.size_mb - b.size_mb)
    .map(m => {
      const dashIdx = m.variant.indexOf('-')
      const size  = m.variant.slice(0, dashIdx)
      const quant = m.variant.slice(dashIdx + 1)
      const sizeGb = (m.size_mb / 1024).toFixed(1)
      const desc = m.description ? `${sizeGb} GB · ${m.description}` : `${sizeGb} GB`
      const key = `${m.family}:${size}:${quant}`
      return { value: key, label: m.label, desc, badge: m.downloaded ? 'ok' as const : 'err' as const }
    })
)

async function loadTranslateModels() {
  try {
    const statusRes = await apiFetch('/setup/status')
    if (statusRes.ok) {
      const s = await statusRes.json()
      translateEnvAvailable.value = s.ai_env_ready ?? null
    }
    await modelStore.fetchModels()

    // 從 localStorage 還原上次選擇
    const saved = loadPreferences()
    if (saved && translateModelOptions.value.some(m => m.value === saved)) {
      selectedTranslateModel.value = saved
    }
  } catch {}
}

// ── localStorage 持久化 ────────────────────────────────────────────────────

const STORAGE_KEY = 'doc-translate-preferences'

function savePreferences() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ translateModel: selectedTranslateModel.value }))
}
function loadPreferences(): string | null {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (!saved) return null
  try { return JSON.parse(saved).translateModel ?? null } catch { return null }
}

watch(selectedTranslateModel, savePreferences)

// ── 語言 ──────────────────────────────────────────────────────────────────

const sourceLanguage = ref('en')
const targetLanguage = ref('zh-TW')
const translateLanguages = ref<{ code: string; name: string }[]>([])

const languageOptions = computed(() =>
  translateLanguages.value.map(l => ({ value: l.code, label: l.name }))
)

async function loadLanguages() {
  try {
    const res = await apiFetch('/document/translategemma/languages')
    if (res.ok) translateLanguages.value = await res.json()
  } catch {}
}

// ── 翻譯風格 ──────────────────────────────────────────────────────────────

const translateStyle = ref('colloquial')
const translateStyles = ref<{ value: string; label: string }[]>([])

async function loadTranslateStyles() {
  try {
    const res = await apiFetch('/setup/translate-styles')
    if (res.ok) translateStyles.value = await res.json()
  } catch {}
}

// ── 專有名詞字典 ──────────────────────────────────────────────────────────

const glossaryText = ref('')

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

// ── 安裝 ──────────────────────────────────────────────────────────────────

async function installTranslate() {
  isInstalling.value = true
  error.value = null
  try {
    const response = await apiFetch('/setup/install', {
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
      await loadTranslateModels()
      return
    }
    taskStore.addTask({
      taskId: result.task_id, taskType: 'setup/install', status: 'pending',
      progress: 0, message: null, result: null, error: null,
      createdAt: new Date(), updatedAt: new Date(), label: '安裝翻譯功能',
    })
    toast.show('開始安裝翻譯功能，請稍候...', { type: 'info', icon: 'bi-download' })
    const checkDone = setInterval(async () => {
      const task = taskStore.tasks.get(result.task_id)
      if (task && (task.status === 'completed' || task.status === 'failed')) {
        clearInterval(checkDone)
        isInstalling.value = false
        if (task.status === 'completed') {
          toast.show('翻譯功能安裝完成', { type: 'success' })
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

// ── 執行 ──────────────────────────────────────────────────────────────────

const isDisabled = computed(() => !props.fileId || isProcessing.value || translateEnvAvailable.value === false)
const isLoading  = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return
  const [tmType, tmSize, tmQuant] = selectedTranslateModel.value.split(':')
  const body: Record<string, any> = {
    file_id: props.fileId,
    source_language: sourceLanguage.value,
    target_language: targetLanguage.value,
    model_type: tmType,
    model_size: tmSize,
    quantization: tmQuant,
    translate_style: translateStyle.value,
  }
  const glossary = parseGlossary()
  if (glossary) body.glossary = glossary

  const taskId = await submitTask('/document/translate', body, '文件翻譯', 'document.translate', props.currentFileName)
  if (taskId) emit('submit', taskId)
}

onMounted(() => { loadTranslateModels(); loadLanguages(); loadTranslateStyles() })

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-translate me-2"></i>翻譯設定
    </h6>
    <p class="form-hint">使用 AI 翻譯文件內容，支援多種語言與翻譯風格。</p>

    <div v-if="error" class="info-box info-box--error">
      <i class="bi bi-exclamation-circle"></i>
      <span>{{ error }}</span>
    </div>

    <!-- 未安裝：顯示安裝按鈕 -->
    <div v-if="translateEnvAvailable === false" class="install-prompt">
      <p class="form-hint">翻譯功能需要 AI 推理環境，首次使用前請先安裝</p>
      <button class="btn-primary" :disabled="isInstalling" @click="installTranslate">
        <span v-if="isInstalling" class="spinner-border spinner-border-sm"></span>
        <i v-else class="bi bi-download"></i>
        {{ isInstalling ? '安裝中...' : '安裝翻譯功能' }}
      </button>
    </div>

    <template v-else>
      <!-- 翻譯模型 -->
      <div class="form-group">
        <label>翻譯模型</label>
        <AppSelect v-model="selectedTranslateModel" :options="translateModelOptions" size="sm" />
      </div>

      <!-- 來源語言 -->
      <div class="form-group">
        <label>來源語言</label>
        <AppSelect v-model="sourceLanguage" :options="languageOptions" size="sm" />
      </div>

      <!-- 目標語言 -->
      <div class="form-group">
        <label>目標語言</label>
        <AppSelect v-model="targetLanguage" :options="languageOptions" size="sm" />
      </div>

      <!-- 翻譯風格 -->
      <div class="form-group">
        <label>翻譯風格</label>
        <AppSelect v-model="translateStyle" :options="translateStyles" size="sm" />
      </div>

      <!-- 專有名詞字典 -->
      <div class="form-group">
        <label>專有名詞字典 <span class="label-hint">（選填）</span></label>
        <textarea
          v-model="glossaryText"
          class="form-input glossary-input"
          placeholder="每行一條，格式：原文→譯文 或 原文=譯文&#10;例：Apple→蘋果"
          rows="4"
        ></textarea>
      </div>
    </template>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

<style lang="scss" scoped>
.label-hint {
  font-weight: 400;
  font-size: 0.78rem;
  color: var(--text-muted);
}

.install-prompt {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.glossary-input {
  resize: vertical;
  font-family: monospace;
  line-height: 1.6;
}
</style>
