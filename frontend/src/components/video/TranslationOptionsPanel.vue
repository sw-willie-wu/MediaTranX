<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from '@/stores/settings'
import { useModelStore } from '@/stores/models'
import { apiFetch } from '@/composables/useApi'
import { useModelOptions, parseModelValue } from '@/composables/useModelOptions'
import { useRemoteModelStore } from '@/stores/remoteModels'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'

const { t } = useI18n()

const settings = useSettingsStore()
const modelStore = useModelStore()
const remoteStore = useRemoteModelStore()

const enableTranslation = ref(false)
const selectedTranslateModel = ref('')

const localTranslateModelOptions = computed(() =>
  modelStore.byCategory('translate')
    .slice()
    .sort((a, b) => a.size_mb - b.size_mb)
    .map(m => {
      const dashIdx = m.variant.indexOf('-')
      const size = m.variant.slice(0, dashIdx)
      const quant = m.variant.slice(dashIdx + 1)
      const key = `${m.family}:${size}:${quant}`
      return { value: key, label: m.label, sizeMb: m.size_mb, badge: m.downloaded ? 'ok' as const : 'err' as const }
    })
)

// 合併本地 + 雲端 text 模型
const { mergedOptions: translateModelOptions } = useModelOptions('text', localTranslateModelOptions)

watch(localTranslateModelOptions, (options) => {
  if (!selectedTranslateModel.value) {
    const first = options.find(m => m.badge === 'ok')
    if (first) selectedTranslateModel.value = first.value
  }
}, { immediate: true })

const targetLanguage = ref('zh-TW')
const keepNames = ref(true)
const translateStyle = ref('colloquial')
const glossaryText = ref('')

const translateLanguages = ref<{ code: string; name: string }[]>([
  { code: 'zh-TW', name: 'zh-TW' },
  { code: 'zh-CN', name: 'zh-CN' },
  { code: 'en',    name: 'en' },
  { code: 'ja',    name: 'ja' },
  { code: 'ko',    name: 'ko' },
])

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

const targetLanguageOptions = computed(() =>
  translateLanguages.value.map(l => ({
    value: l.code,
    label: l.name,
  }))
)

const STORAGE_KEY = 'translate-preferences'

function savePreferences() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ translateModel: selectedTranslateModel.value }))
}

function loadPreferences(): string | null {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (!saved) return null
  try {
    const parsed = JSON.parse(saved)
    if (parsed.translateModel) return parsed.translateModel
    if (parsed.modelType && parsed.modelSize && parsed.quantization) {
      return `${parsed.modelType}:${parsed.modelSize}:${parsed.quantization}`
    }
  } catch {}
  return null
}

async function autoRecommend() {
  await settings.loadDeviceInfo()
  const totalBytes = settings.deviceInfo?.memory_total
  if (!totalBytes) return
  const usableMb = totalBytes / (1024 * 1024) - 1500
  const sorted = [...localTranslateModelOptions.value]
    .filter(m => m.badge === 'ok')
    .sort((a, b) => (b.sizeMb ?? 0) - (a.sizeMb ?? 0))
  const best = sorted.find(m => (m.sizeMb ?? 0) <= usableMb)
  if (best) selectedTranslateModel.value = best.value
}

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

async function loadTranslateModels() {
  try {
    await modelStore.fetchModels()
  } catch {}
}

async function loadTranslateLanguages(retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      const response = await apiFetch('/video/translategemma/languages')
      if (response.ok) { translateLanguages.value = await response.json(); return }
    } catch {}
    if (i < retries - 1) await new Promise(r => setTimeout(r, 1000))
  }
}

watch(enableTranslation, (val) => { if (val) loadTranslateLanguages() })
watch(selectedTranslateModel, savePreferences)

onMounted(async () => {
  await Promise.all([loadTranslateModels(), loadTranslateStyles()])
  remoteStore.fetchAll()
  settings.loadDeviceInfo()
  const saved = loadPreferences()
  if (saved && localTranslateModelOptions.value.some(m => m.value === saved)) {
    selectedTranslateModel.value = saved
  } else if (saved && saved.startsWith('remote:')) {
    selectedTranslateModel.value = saved
  } else {
    await autoRecommend()
  }
})

defineExpose({
  enableTranslation,
  targetLanguage,
  selectedTranslateModel,
  keepNames,
  translateStyle,
  parseGlossary,
})
</script>

<template>
  <div class="form-group">
    <AppToggle v-model="enableTranslation">{{ $t('video.translate.enable') }}</AppToggle>

    <div v-if="enableTranslation" class="sub-params">
        <div class="form-group">
          <label class="sub-label">{{ $t('video.translate.target_language') }}</label>
          <AppSelect v-model="targetLanguage" :options="targetLanguageOptions" />
        </div>

        <div v-if="!selectedTranslateModel && !modelStore.loading" class="info-box info-box--warn">
          <i class="bi bi-exclamation-triangle"></i>
          <span>{{ $t('video.translate.no_model_downloaded') }}</span>
        </div>
        <div class="form-group">
          <label class="sub-label">{{ $t('video.translate.model') }}</label>
          <AppSelect v-model="selectedTranslateModel" :options="translateModelOptions" />
        </div>

        <div class="form-group">
          <label class="sub-label">{{ $t('video.translate.style') }}</label>
          <AppSelect v-model="translateStyle" :options="translateStyles" />
        </div>

        <div class="option-row">
          <AppToggle v-model="keepNames">{{ $t('video.translate.keep_names') }}</AppToggle>
          <span class="form-hint">{{ $t('video.translate.keep_names_hint') }}</span>
        </div>

        <div class="form-group">
          <label class="sub-label">{{ $t('video.translate.glossary') }}</label>
          <textarea
            v-model="glossaryText"
            class="form-input glossary-input"
            rows="3"
            :placeholder="$t('video.translate.glossary_format')"
          ></textarea>
        </div>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

<style lang="scss" scoped>
.option-row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.glossary-input {
  resize: vertical;
  font-family: monospace;
  line-height: 1.6;
}
</style>
