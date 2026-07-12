<script setup lang="ts">
/**
 * audio.transcribe 參數元件（統一參數元件 spec §5；批 3 Task 3.4——批 3 最大工具）。
 * UI 沿舊 components/audio/panels/AudioTranscribePanel.vue：model/source_language/
 * output_format 三個 top-level form-group；TranslationOptionsPanel（內嵌、受控 v-model）
 * top-level（非 SettingsCollapsible，同舊 panel）；summarize toggle + AppSelect（頂層，同舊
 * panel）；vocal_separation + WhisperAdvancedSettings 進 SettingsCollapsible 進階區（沿佈局
 * 鐵則——舊 panel SettingsCollapsible 範圍）。
 *
 * 與 SubtitleParams.vue 的關鍵差異（見 transcribe.meta.ts 檔頭「與 video.subtitle 的關鍵差異」）：
 * 1. 翻譯 gate＝獨立 `translate` bool 欄位（非「target_language 非空」判準）——
 *    TranslationOptionsPanel 受控 modelValue 的 enable_translation 直接對映 params.translate，
 *    onTranslationChange() 明確寫 translate:true/false（subtitle 沒有這個欄位）。
 * 2. 多一組 summarize（第三 composite，subtitle/summary 皆無）：toggle + AppSelect，本地
 *    token 拆解沿 TranslationOptionsPanel.localTranslateModelOptions 同款 pattern（含
 *    quantization，非 SummaryParams 的 llm/vlm 兩段無 quant 格式——recon §5 已核實，見
 *    transcribe.meta.ts 檔頭）；seed/auto-select 沿 SummaryParams 的 modelPickerSeeded flag
 *    pattern（非舊 AudioTranscribePanel 的無旗標寫法——批 1 review 已定案的已知地雷，見
 *    common-constraints.md「composite commitPatch 的 emit 不同步反映到 props」）。
 * 3. source_language 選項：本檔選擇**元件內 onMounted 載入、且僅 context==='tool' 才發
 *    GET /audio/transcribe/languages**（pipeline 節點表單不發此 GET，退純文字輸入）——與
 *    SubtitleParams.vue 由外層殼（SubtitlePanel.vue 例外殼）傳 languageOptions prop 的作法不同；
 *    transcribe 走標準 ToolParamHost、無殼可傳 prop，見 task report 決策說明。
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import type { SelectItem, SelectOption } from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import WhisperAdvancedSettings, { type WhisperAdvancedValue } from '@/components/video/WhisperAdvancedSettings.vue'
import TranslationOptionsPanel, { type TranslationOptionsValue } from '@/components/video/TranslationOptionsPanel.vue'
import { useModelStore } from '@/stores/models'
import { useRemoteModelStore } from '@/stores/remoteModels'
import { useModelOptions } from '@/composables/useModelOptions'
import { usePersistedModel } from '@/composables/usePersistedModel'
import { apiFetch } from '@/composables/useApi'
import type { AgentCompositeField } from '../types'
import {
  META as TRANSCRIBE_META,
  TRANSLATE_FIELDS,
  SUMMARIZE_FIELDS,
  encodeSubModelToken,
  decodeSubModelToken,
} from './transcribe.meta'

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
}>()
const emit = defineEmits<{ 'update:params': [Record<string, unknown>] }>()

const { t } = useI18n()

function commit(next: Record<string, unknown>) {
  emit('update:params', next)
}
function commitPatch(patch: Record<string, unknown>) {
  commit({ ...props.params, ...patch })
}

function flattenTokens(items: SelectItem[]): string[] {
  return items.flatMap((o) => ('options' in o ? o.options.map((x) => x.value) : [o.value]))
}

// ── model stores（新元件掛載必呼 ensureLoaded——沿批 2/3 既有慣例） ─────────────
const modelStore = useModelStore()
const remoteStore = useRemoteModelStore()
onMounted(() => {
  modelStore.ensureLoaded()
  remoteStore.ensureLoaded()
})

// ══ Whisper picker（單欄 composite，token=variant；欄位名 model_size） ═══════════
const whisperModelOptions = computed<SelectOption[]>(() =>
  modelStore.forPanel(modelStore.byCategory('stt')).map((m) => ({
    value: m.variant,
    label: m.label,
    badge: (m.downloaded ? 'ok' : 'err') as 'ok' | 'err',
  })),
)

const whisperToken = computed(() => String(props.params.model_size ?? ''))

function onWhisperTokenChange(token: string) {
  commitPatch({ model_size: token })
  if (props.context === 'tool') persistedWhisper.value = token
}

const persistedWhisper = usePersistedModel('transcribe_whisper_model', '', { enabled: props.context === 'tool' })
const defaultWhisperToken = String(TRANSCRIBE_META.defaults().model_size ?? '')
let whisperSeeded = false

if (props.context === 'tool' && persistedWhisper.value && whisperToken.value === defaultWhisperToken) {
  commitPatch({ model_size: persistedWhisper.value })
  whisperSeeded = true
}

watch(
  whisperModelOptions,
  (options) => {
    if (props.context !== 'tool') return
    if (whisperSeeded) return
    if (options.length === 0) return
    if (options.some((o) => o.value === whisperToken.value)) return
    const first = options.find((o) => o.badge === 'ok')
    if (first) {
      onWhisperTokenChange(first.value)
      whisperSeeded = true
    }
  },
  { immediate: true },
)

// ── output_format（頂層 enum，txt/srt——vs subtitle 的 srt/vtt） ─────────────────
const outputFormatOptions = computed<SelectOption[]>(() => [
  { value: 'txt', label: t('audio.transcribe.txt_format') },
  { value: 'srt', label: t('audio.transcribe.srt_format') },
])
function onOutputFormatChange(v: string) {
  commitPatch({ output_format: v })
}

// ── source_language（元件內載入，僅 context==='tool' 才發 GET；pipeline 退純文字輸入） ──
const rawLanguages = ref<{ value: string; label: string }[]>([])
async function loadLanguages() {
  try {
    const res = await apiFetch('/audio/transcribe/languages')
    if (res.ok) rawLanguages.value = await res.json()
  } catch {
    // 靜默失敗（沿舊 panel 行為）——退純文字輸入分支仍可用
  }
}
onMounted(() => {
  if (props.context === 'tool') loadLanguages()
})
const languageOptions = computed<SelectOption[]>(() =>
  rawLanguages.value.map((item) => (item.value === '' ? { ...item, label: t('common.auto_detect') } : item)),
)
const hasLanguageOptions = computed(() => languageOptions.value.length > 0)
function onSourceLanguageChange(v: string) {
  commitPatch({ source_language: v })
}

// ══ 翻譯區塊：內嵌 TranslationOptionsPanel（受控 modelValue）══════════════════════
// gate = params.translate（獨立 bool 欄位，非 subtitle 的 target_language 非空判準——見檔頭註解）。
const translationValue = computed<TranslationOptionsValue>(() => ({
  enable_translation: props.params.translate === true,
  target_language: String(props.params.target_language ?? ''),
  translate_model_token: encodeSubModelToken(props.params, 'translate'),
  keep_names: props.params.keep_names !== false,
  translate_style: String(props.params.translate_style ?? 'colloquial'),
  glossary_text: glossaryToText(props.params.glossary),
}))

function glossaryToText(g: unknown): string {
  if (!g || typeof g !== 'object') return ''
  return Object.entries(g as Record<string, string>)
    .map(([src, tgt]) => `${src} → ${tgt}`)
    .join('\n')
}

function parseGlossaryText(text: string): Record<string, string> | undefined {
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

function onTranslationChange(v: TranslationOptionsValue) {
  if (!v.enable_translation) {
    // gate 關閉 → translate 明確寫 false + 清空全部 translate_* + keep_names/translate_style/
    // glossary（undefined 覆蓋殘值，語意同 subtitle.meta.ts decodeTranslateToken 檔頭註解）。
    commitPatch({
      translate: false,
      target_language: undefined,
      keep_names: undefined,
      translate_style: undefined,
      glossary: undefined,
      translate_model_family: undefined,
      translate_model_size: undefined,
      translate_quantization: undefined,
      translate_remote: undefined,
      translate_provider: undefined,
      translate_conn_id: undefined,
      translate_remote_model: undefined,
    })
    return
  }
  commitPatch({
    translate: true,
    target_language: v.target_language || 'zh-TW',
    keep_names: v.keep_names,
    translate_style: v.translate_style,
    glossary: parseGlossaryText(v.glossary_text),
    ...decodeSubModelToken(v.translate_model_token, 'translate'),
  })
}

// translate model picker options（供 composite agent 欄位讀取；TranslationOptionsPanel 額外
// expose 的 translateModelOptions，經 template ref 讀取，同 SubtitleParams.vue pattern）。
const translationPanelRef = ref<{ translateModelOptions?: SelectItem[] } | null>(null)

// ══ 摘要區塊：toggle + AppSelect（第三 composite，subtitle/summary 皆無） ══════════════
function onSummarizeToggle(v: boolean) {
  commitPatch({ summarize: v })
}

const localSummarizeOptions = computed<SelectOption[]>(() =>
  modelStore.forPanel(modelStore.byCapability('text'))
    .slice()
    .sort((a, b) => a.size_mb - b.size_mb)
    .map((m) => {
      const [size, quant] = m.variant.split(':')
      const key = `${m.family}:${size}:${quant}`
      return { value: key, label: m.label, sizeMb: m.size_mb, badge: (m.downloaded ? 'ok' : 'err') as 'ok' | 'err' }
    }),
)
const { mergedOptions: summarizeModelOptions } = useModelOptions('text', localSummarizeOptions)

const summarizeToken = computed(() => encodeSubModelToken(props.params, 'summarize'))

function onSummarizeTokenChange(token: string) {
  commitPatch(decodeSubModelToken(token, 'summarize'))
  if (props.context === 'tool') persistedSummarize.value = token
}

const persistedSummarize = usePersistedModel('transcribe_summarize_model', '', { enabled: props.context === 'tool' })
const defaultSummarizeToken = encodeSubModelToken(TRANSCRIBE_META.defaults(), 'summarize')
let summarizeSeeded = false

if (props.context === 'tool' && persistedSummarize.value && summarizeToken.value === defaultSummarizeToken) {
  commitPatch(decodeSubModelToken(persistedSummarize.value, 'summarize'))
  summarizeSeeded = true
}

watch(
  localSummarizeOptions,
  (options) => {
    if (props.context !== 'tool') return
    if (summarizeSeeded) return
    if (options.length === 0) return
    if (flattenTokens(summarizeModelOptions.value).includes(summarizeToken.value)) return
    const first = options.find((o) => o.badge === 'ok')
    if (first) {
      onSummarizeTokenChange(first.value)
      summarizeSeeded = true
    }
  },
  { immediate: true },
)

// ══ vocal_separation / WhisperAdvancedSettings（v-model 化，advanced 區） ══════════════
function onVocalSeparationChange(v: boolean) {
  commitPatch({ vocal_separation: v })
}

const whisperAdvancedValue = computed<WhisperAdvancedValue>(() => ({
  word_timestamps: Boolean(props.params.word_timestamps),
  align: Boolean(props.params.align),
  condition_on_previous_text: props.params.condition_on_previous_text !== false,
  min_silence_duration_ms: Number(props.params.min_silence_duration_ms ?? 200),
  vad_threshold: Number(props.params.vad_threshold ?? 0.3),
}))

function onWhisperAdvancedChange(v: WhisperAdvancedValue) {
  commitPatch({
    word_timestamps: v.word_timestamps,
    align: v.align,
    condition_on_previous_text: v.condition_on_previous_text,
    min_silence_duration_ms: v.min_silence_duration_ms,
    vad_threshold: v.vad_threshold,
  })
}

// ── composite 註冊（whisper_model 單欄；translate_model／summarize_model 各七欄） ────────
const registerComposite = inject<(c: AgentCompositeField) => () => void>('registerComposite')
registerComposite?.({
  name: 'whisper_model',
  covers: ['model_size'],
  options: () => whisperModelOptions.value.map((o) => o.value),
  get: (p) => String(p.model_size ?? ''),
  set: (token) => ({ model_size: token }),
})
registerComposite?.({
  name: 'translate_model',
  covers: [...TRANSLATE_FIELDS],
  options: () => flattenTokens(translationPanelRef.value?.translateModelOptions ?? []),
  get: (p) => (p.translate === true ? encodeSubModelToken(p, 'translate') : ''),
  set: (token) => decodeSubModelToken(token, 'translate'),
})
registerComposite?.({
  name: 'summarize_model',
  covers: [...SUMMARIZE_FIELDS],
  options: () => flattenTokens(summarizeModelOptions.value),
  get: (p) => (p.summarize === true ? encodeSubModelToken(p, 'summarize') : ''),
  set: (token) => decodeSubModelToken(token, 'summarize'),
})
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-mic-fill me-2"></i>{{ $t('audio.transcribe.title') }}
    </h6>
    <p class="form-hint">{{ $t('audio.transcribe.description') }}</p>

    <div class="form-group">
      <label>{{ $t('audio.transcribe.model') }}</label>
      <AppSelect
        :modelValue="whisperToken"
        :options="whisperModelOptions"
        :placeholder="$t('common.no_models_available')"
        @update:modelValue="onWhisperTokenChange"
      />
    </div>

    <div class="form-group">
      <label>{{ $t('common.source_language') }}</label>
      <AppSelect
        v-if="hasLanguageOptions"
        :modelValue="String(params.source_language ?? '')"
        :options="languageOptions"
        @update:modelValue="onSourceLanguageChange"
      />
      <input
        v-else
        type="text"
        class="form-input"
        :value="String(params.source_language ?? '')"
        :placeholder="$t('audio.transcribe.source_language_placeholder')"
        @change="(e) => onSourceLanguageChange((e.target as HTMLInputElement).value)"
      />
    </div>

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect
        :modelValue="String(params.output_format ?? 'txt')"
        :options="outputFormatOptions"
        @update:modelValue="onOutputFormatChange"
      />
    </div>

    <TranslationOptionsPanel
      ref="translationPanelRef"
      storage-key="audio_transcribe_translate_model"
      :context="context"
      :model-value="translationValue"
      @update:model-value="onTranslationChange"
    />

    <div class="form-group">
      <AppToggle :modelValue="Boolean(params.summarize)" @update:modelValue="onSummarizeToggle">
        {{ $t('audio.transcribe.generate_outline') }}
      </AppToggle>
      <small class="form-hint">{{ $t('audio.transcribe.generate_outline_hint') }}</small>
    </div>

    <div v-if="params.summarize" class="form-group">
      <label>{{ $t('audio.transcribe.outline_model') }}</label>
      <AppSelect :modelValue="summarizeToken" :options="summarizeModelOptions" @update:modelValue="onSummarizeTokenChange" />
    </div>

    <SettingsCollapsible storage-key="audio_transcribe_advanced">
      <div class="form-group">
        <AppToggle :modelValue="Boolean(params.vocal_separation)" @update:modelValue="onVocalSeparationChange">
          {{ $t('audio.transcribe.vocal_separation') }}
        </AppToggle>
        <small class="form-hint">{{ $t('audio.transcribe.vocal_separation_hint') }}</small>
      </div>

      <WhisperAdvancedSettings :embedded="true" :model-value="whisperAdvancedValue" @update:model-value="onWhisperAdvancedChange" />
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
