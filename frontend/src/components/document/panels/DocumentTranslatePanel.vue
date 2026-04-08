<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import { apiFetch } from '@/composables/useApi'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useModelStore } from '@/stores/models'
import { useModelOptions, parseModelValue } from '@/composables/useModelOptions'
import { useRemoteModelStore } from '@/stores/remoteModels'
import { useModelGuard } from '@/composables/useModelGuard'
import { usePersistedModel } from '@/composables/usePersistedModel'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()
const modelStore = useModelStore()
const remoteStore = useRemoteModelStore()
const { guardModelReady } = useModelGuard()

// ── 翻譯模型（從 modelStore 取得）────────────────────────────────────────

const selectedTranslateModel = usePersistedModel('doc_translate_model')
const error = ref<string | null>(null)

const localTranslateModelOptions = computed(() =>
  modelStore.forPanel(modelStore.byCapability('text'))
    .slice()
    .sort((a, b) => a.size_mb - b.size_mb)
    .map(m => {
      const [size, quant] = m.variant.split(':')
      const key = `${m.family}:${size}:${quant}`
      return { value: key, label: m.label, sizeMb: m.size_mb, badge: m.downloaded ? 'ok' as const : 'err' as const }
    })
)

// 合併本地 + 雲端 text 模型
const { mergedOptions: translateModelOptions } = useModelOptions('text', localTranslateModelOptions)

watch(localTranslateModelOptions, (options) => {
  if (!selectedTranslateModel.value || !options.some(m => m.value === selectedTranslateModel.value)) {
    const first = options.find(m => m.badge === 'ok')
    selectedTranslateModel.value = first?.value ?? ''
  }
}, { immediate: true })

async function loadTranslateModels() {
  try {
    await modelStore.fetchModels()

    // 從 localStorage 還原上次選擇
    const saved = loadPreferences()
    if (saved && localTranslateModelOptions.value.some(m => m.value === saved && m.badge === 'ok')) {
      selectedTranslateModel.value = saved
    } else if (saved && saved.startsWith('remote:')) {
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
const rawTranslateStyles = ref<{ value: string; label: string }[]>([])

const styleI18nKey: Record<string, string> = {
  colloquial: 'video.translate.style_colloquial',
  formal: 'video.translate.style_formal',
  literal: 'video.translate.style_literal',
}

const translateStyles = computed(() =>
  rawTranslateStyles.value.map(item => ({
    ...item,
    label: styleI18nKey[item.value] ? t(styleI18nKey[item.value]) : item.label,
  }))
)

async function loadTranslateStyles() {
  try {
    const res = await apiFetch('/setup/translate-styles')
    if (res.ok) rawTranslateStyles.value = await res.json()
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

// ── 執行 ──────────────────────────────────────────────────────────────────

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

async function execute() {
  const parsed = parseModelValue(selectedTranslateModel.value)
  const isModelReady = parsed.isRemote || localTranslateModelOptions.value.find(m => m.value === selectedTranslateModel.value)?.badge === 'ok'
  if (!await guardModelReady(isModelReady === true, 'llm')) return
  if (!props.fileId || !selectedTranslateModel.value) return
  const body: Record<string, any> = {
    file_id: props.fileId,
    source_language: sourceLanguage.value,
    target_language: targetLanguage.value,
    translate_style: translateStyle.value,
  }

  if (parsed.isRemote) {
    body.remote = true
    body.provider = parsed.provider
    body.conn_id = parsed.connId
    body.remote_model = parsed.modelId
  } else {
    const [tmType, tmSize, tmQuant] = selectedTranslateModel.value.split(':')
    body.model_type = tmType
    body.model_size = tmSize
    body.quantization = tmQuant
  }

  const glossary = parseGlossary()
  if (glossary) body.glossary = glossary

  const taskId = await submitTask('/document/translate', body, t('document.translate.task_label'), 'document.translate', props.currentFileName)
  if (taskId) emit('submit', taskId)
}

onMounted(() => { loadTranslateModels(); loadLanguages(); loadTranslateStyles(); remoteStore.fetchAll() })

function getParams() {
  const parsed = parseModelValue(selectedTranslateModel.value)
  const body: Record<string, any> = {
    source_language: sourceLanguage.value,
    target_language: targetLanguage.value,
    translate_style: translateStyle.value,
  }

  if (parsed.isRemote) {
    body.remote = true
    body.provider = parsed.provider
    body.conn_id = parsed.connId
    body.remote_model = parsed.modelId
  } else {
    const [tmType, tmSize, tmQuant] = selectedTranslateModel.value.split(':')
    body.model_type = tmType
    body.model_size = tmSize
    body.quantization = tmQuant
  }

  const glossary = parseGlossary()
  if (glossary) body.glossary = glossary

  return body
}

defineExpose({ execute, isDisabled, isLoading, getParams })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-translate me-2"></i>{{ $t('document.translate.title') }}
    </h6>
    <p class="form-hint">{{ $t('document.translate.description') }}</p>

    <div v-if="error" class="info-box info-box--error">
      <i class="bi bi-exclamation-circle"></i>
      <span>{{ error }}</span>
    </div>

      <!-- 翻譯模型 -->
      <div class="form-group">
        <label>{{ $t('document.translate.model') }}</label>
        <AppSelect v-model="selectedTranslateModel" :options="translateModelOptions" />
      </div>

      <!-- 來源語言 -->
      <div class="form-group">
        <label>{{ $t('document.translate.source_language') }}</label>
        <AppSelect v-model="sourceLanguage" :options="languageOptions" />
      </div>

      <!-- 目標語言 -->
      <div class="form-group">
        <label>{{ $t('document.translate.target_language') }}</label>
        <AppSelect v-model="targetLanguage" :options="languageOptions" />
      </div>

      <!-- 翻譯風格 -->
      <div class="form-group">
        <label>{{ $t('document.translate.style') }}</label>
        <AppSelect v-model="translateStyle" :options="translateStyles" />
      </div>

      <!-- 專有名詞字典 -->
      <div class="form-group">
        <label>{{ $t('document.translate.glossary') }} <span class="label-hint">{{ $t('document.translate.optional') }}</span></label>
        <textarea
          v-model="glossaryText"
          class="form-input glossary-input"
          :placeholder="$t('document.translate.glossary_format')"
          rows="4"
        ></textarea>
      </div>
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

.glossary-input {
  resize: vertical;
  font-family: monospace;
  line-height: 1.6;
}
</style>
