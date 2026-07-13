<script setup lang="ts">
/**
 * TranslationOptionsPanel — video.subtitle 翻譯區塊子元件（統一參數元件 spec §5；批 2 Task
 * 2.5 v-model 化；收尾批 W1-2 移除雙軌相容——AudioTranscribePanel.vue／AudioLyricsPanel.vue
 * 兩個舊 uncontrolled 呼叫端已在批 3 遷移時整檔刪除；現存三個消費者
 * （SubtitleParams.vue／TranscribeParams.vue／LyricsParams.vue）**皆**以
 * `:model-value="translationValue"` 受控掛載——`modelValue` 恆有值，
 * 元件內部不再區分受控/非受控兩種模式。
 *
 * 內部狀態初值來自 modelValue，之後外部寫入（watch props.modelValue）與內部使用者操作
 * （watch 6 個狀態 → emit update:modelValue）雙向同步；one-shot lastEmitted echo 判別沿
 * CutParams.vue/WhisperAdvancedSettings.vue pattern。selectedTranslateModel 若 modelValue.
 * translate_model_token 非空,以此為準覆蓋 usePersistedModel 的 localStorage 初值,並跳過
 * onMounted 的 loadPreferences/autoRecommend 自動校正（避免父層已有明確初值時被 localStorage
 * 殘值蓋掉——見 controlledSeeded 旗標）。
 *
 * `context` prop（預設 'tool'）：僅影響內部 usePersistedModel 的 enabled 開關——pipeline
 * 語境不讀寫 localStorage（沿統一參數元件案全域鐵則）。
 *
 * 已知限制（out of scope,未修）：下方既有的 `watch(localTranslateModelOptions, ..., {immediate:
 * true})` fallback（雙軌化之前就有,非本次改動範圍）在 modelValue 提供的 translate_model_token
 * 尚未出現在當下已載入的 options 清單中時，會把它蓋成「第一個已下載模型」——與 controlledSeeded
 * 對 onMounted 段的保護是兩條獨立路徑，controlledSeeded 不覆蓋這個既有 watch。只有當 seeded
 * token 本身確實對應到一個已存在於選項清單的模型時才穩定生效；這與雙軌化之前「localStorage
 * 殘留 token 若尚未載入清單也會被清空」的既有 quirk 同構，不是本次新增的迴歸。
 */
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from '@/stores/settings'
import { useModelStore } from '@/stores/models'
import { apiFetch } from '@/composables/useApi'
import { useModelOptions } from '@/composables/useModelOptions'
import { useRemoteModelStore } from '@/stores/remoteModels'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import { usePersistedModel } from '@/composables/usePersistedModel'

export interface TranslationOptionsValue {
  enable_translation: boolean
  target_language: string
  translate_model_token: string
  keep_names: boolean
  translate_style: string
  glossary_text: string
}

const props = withDefaults(
  defineProps<{ storageKey?: string; context?: 'tool' | 'pipeline'; modelValue?: TranslationOptionsValue }>(),
  { storageKey: 'subtitle_translate_model', context: 'tool' },
)
const emit = defineEmits<{ 'update:modelValue': [TranslationOptionsValue] }>()

const { t } = useI18n()

const settings = useSettingsStore()
const modelStore = useModelStore()
const remoteStore = useRemoteModelStore()

const enableTranslation = ref(props.modelValue?.enable_translation ?? false)
const selectedTranslateModel = usePersistedModel(props.storageKey, '', { enabled: () => props.context === 'tool' })

// 受控且父層已提供非空 token → 以父層值為準（蓋過 usePersistedModel 的 localStorage 初值），
// 並標記旗標讓 onMounted 的 loadPreferences/autoRecommend 自動校正跳過（見檔頭註解）。
let controlledSeeded = false
if (props.modelValue?.translate_model_token) {
  selectedTranslateModel.value = props.modelValue.translate_model_token
  controlledSeeded = true
}

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

const targetLanguage = ref(props.modelValue?.target_language || 'zh-TW')
const keepNames = ref(props.modelValue?.keep_names ?? true)
const translateStyle = ref(props.modelValue?.translate_style ?? 'colloquial')
const glossaryText = ref(props.modelValue?.glossary_text ?? '')

const translateLanguages = ref<{ code: string; name: string }[]>([
  { code: 'zh-TW', name: 'zh-TW' },
  { code: 'zh-CN', name: 'zh-CN' },
  { code: 'en',    name: 'en' },
  { code: 'ja',    name: 'ja' },
  { code: 'ko',    name: 'ko' },
])

const rawTranslateStyles = ref<{ value: string; label: string }[]>([])

const styleI18nKey: Record<string, string> = {
  colloquial: 'common.translate_style_colloquial',
  formal: 'common.translate_style_formal',
  literal: 'common.translate_style_literal',
}

const translateStyles = computed(() =>
  rawTranslateStyles.value.map(item => ({
    ...item,
    label: styleI18nKey[item.value] ? t(styleI18nKey[item.value]) : item.label,
  }))
)

async function loadTranslateStyles() {
  try {
    const res = await apiFetch('/llm/translate/styles')
    if (res.ok) rawTranslateStyles.value = await res.json()
  } catch {}
}

const targetLanguageOptions = computed(() =>
  translateLanguages.value.map(l => ({
    value: l.code,
    label: l.name,
  }))
)

const STORAGE_KEY = `translate-preferences-${props.storageKey}`

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

/** 純函式版本（不依賴 glossaryText ref）——供 parseGlossary() 與 modelValue watch 的
 * dict 等價判斷共用（見 :287 附近註解，C1 修復）。 */
function parseGlossaryString(text: string): Record<string, string> | undefined {
  const trimmed = text.trim()
  if (!trimmed) return undefined
  const dict: Record<string, string> = {}
  for (const line of trimmed.split('\n')) {
    const l = line.trim()
    if (!l) continue
    const sep = l.includes('→') ? '→' : '='
    const parts = l.split(sep)
    if (parts.length >= 2) {
      const src = parts[0].trim()
      const tgt = parts.slice(1).join(sep).trim()
      if (src && tgt) dict[src] = tgt
    }
  }
  return Object.keys(dict).length > 0 ? dict : undefined
}

function parseGlossary(): Record<string, string> | undefined {
  return parseGlossaryString(glossaryText.value)
}

/** 兩段 glossary 原始文字解析出的 dict 是否等價（key/value 逐一比對，undefined 視為空 dict）。
 * 用於 modelValue watch 判斷「父層回流值」是否只是使用者當下輸入的正規化／未完成版本
 * （見 C1 修復註解）。 */
function glossaryEquivalent(a: string, b: string): boolean {
  const da = parseGlossaryString(a)
  const db = parseGlossaryString(b)
  if (!da && !db) return true
  if (!da || !db) return false
  const keysA = Object.keys(da)
  const keysB = Object.keys(db)
  if (keysA.length !== keysB.length) return false
  return keysA.every((k) => da[k] === db[k])
}

async function loadTranslateModels() {
  try {
    await modelStore.fetchModels()
  } catch {}
}

async function loadTranslateLanguages(retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      const response = await apiFetch('/llm/translate/languages')
      if (response.ok) { translateLanguages.value = await response.json(); return }
    } catch {}
    if (i < retries - 1) await new Promise(r => setTimeout(r, 1000))
  }
}

watch(enableTranslation, (val) => { if (val) loadTranslateLanguages() })
watch(selectedTranslateModel, savePreferences)

onMounted(async () => {
  await Promise.all([loadTranslateModels(), loadTranslateStyles()])
  remoteStore.ensureLoaded()
  settings.loadDeviceInfo()
  // 受控且父層已餵過明確初值（controlledSeeded）→ 不跑 localStorage 還原/自動推薦，
  // 避免蓋掉父層（SubtitleParams）已經同步好的 params 衍生值（見檔頭註解）。
  if (controlledSeeded) return
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
  targetLanguageOptions,
  // 批 2 Task 2.5 新增（additive,不影響既有呼叫端）：受控模式下 SubtitleParams 用來組
  // composite agent 欄位的 options() 清單（本地已裝 + 雲端合併後的完整選項）。
  translateModelOptions,
})

function currentValue(): TranslationOptionsValue {
  return {
    enable_translation: enableTranslation.value,
    target_language: targetLanguage.value,
    translate_model_token: selectedTranslateModel.value,
    keep_names: keepNames.value,
    translate_style: translateStyle.value,
    glossary_text: glossaryText.value,
  }
}

function shallowEqualValue(a: TranslationOptionsValue, b: TranslationOptionsValue): boolean {
  return (
    a.enable_translation === b.enable_translation &&
    a.target_language === b.target_language &&
    a.translate_model_token === b.translate_model_token &&
    a.keep_names === b.keep_names &&
    a.translate_style === b.translate_style &&
    a.glossary_text === b.glossary_text
  )
}

let lastEmitted: TranslationOptionsValue | null = null

// 內部 6 個狀態任一變動 → emit 完整 patch（單一受控消費者 SubtitleParams，恆有 modelValue）。
watch([enableTranslation, targetLanguage, selectedTranslateModel, keepNames, translateStyle, glossaryText], () => {
  const next = currentValue()
  lastEmitted = next
  emit('update:modelValue', next)
})

// 外部寫入 props.modelValue（父層 setField/setParams/seed）→ 同步回內部狀態；one-shot echo
// 判別：本次 watch 觸發若等於上次自己 emit 的值，視為回流，不重推（避免迴圈，同
// WhisperAdvancedSettings.vue pattern）。translate_model_token 空字串時不覆蓋 selectedTranslateModel
// （沿 controlledSeeded 同一理由——避免把使用者已選好、gate 剛關閉時的 picker 選擇清空）。
watch(
  () => props.modelValue,
  (v) => {
    if (!v) return
    const echo = lastEmitted
    lastEmitted = null
    if (echo && shallowEqualValue(echo, v)) return
    enableTranslation.value = v.enable_translation
    targetLanguage.value = v.target_language || 'zh-TW'
    if (v.translate_model_token) selectedTranslateModel.value = v.translate_model_token
    keepNames.value = v.keep_names
    translateStyle.value = v.translate_style
    // glossary_text 只在「解析出的 dict 真的不同」時才覆蓋（C1 修復）——父層
    // SubtitleParams 的 translationValue computed 會把 params.glossary（dict）反算成
    // 正規化字串（`=` 統一成 `→`、未完成/無分隔符的行被丟棄），若無條件覆蓋，使用者逐字輸入
    // 尚未成行的內容（如剛打完 "abc"）或格式與正規化輸出不同的已完成行都會被回流的字串
    // 清空/改寫。只有當外部真的改了 glossary（dict 不等價，例如切換檔案/外部 setParams）
    // 才覆蓋成父層值。
    if (!glossaryEquivalent(glossaryText.value, v.glossary_text)) {
      glossaryText.value = v.glossary_text
    }
  },
  { deep: true },
)
</script>

<template>
  <div class="form-group">
    <AppToggle v-model="enableTranslation">{{ $t('video.translate.enable') }}</AppToggle>

    <div v-if="enableTranslation" class="sub-params">
        <div class="form-group">
          <label class="sub-label">{{ $t('common.target_language') }}</label>
          <AppSelect v-model="targetLanguage" :options="targetLanguageOptions" />
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
