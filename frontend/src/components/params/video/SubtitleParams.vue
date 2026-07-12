<script setup lang="ts">
/**
 * video.subtitle 參數元件（統一參數元件 spec §5；批 2 Task 2.5——例外殼工具：本元件是
 * SubtitlePanel.vue 的表單本體，也是 pipeline dispatcher（PipelineParamForm）掛載的節點
 * 表單，但**不經 ToolParamHost**——SubtitlePanel 保留自建 task 的職責（apiFetch+手動
 * taskStore.addTask+自管 isLoading/error+agent host），本元件只管 params 讀寫與 UI。
 *
 * UI 沿舊 components/video/SubtitlePanel.vue：source_language/model_size/output_format 三個
 * top-level form-group；TranslationOptionsPanel（內嵌、受控 v-model）top-level（非
 * SettingsCollapsible，同舊 panel）；vocal_separation + WhisperAdvancedSettings 進
 * SettingsCollapsible 進階區（沿佈局鐵則——舊 panel 沒有的新欄位一律進階區，本工具無新增
 * top-level 欄位，故無此情形）。
 *
 * 翻譯「啟用」gate：無獨立 enable_translation 欄位，以 target_language 是否非空字串代表
 * （見 subtitle.meta.ts 檔頭註解）。onTranslationChange() 據此決定寫入 params 或清空七個
 * translate_* 欄位 + keep_names/translate_style/glossary。
 *
 * source_language 選項由 languageOptions prop 傳入（工具頁殼 SubtitlePanel.vue 呼叫
 * GET /audio/transcribe/languages 載入後傳下；pipeline 語境未傳，退純文字輸入，見底部模板）。
 * 這是本元件唯一超出 {params,context,fileInfo} 標準契約的額外 prop——因為 SubtitlePanel.vue
 * 是手寫模板直接掛載本元件（不經 ToolParamHost 的通用 dispatch），可以自由多傳；
 * PipelineParamForm 的通用 dispatch 不會傳這個 prop，元件需妥善處理其缺席。
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
import { usePersistedModel } from '@/composables/usePersistedModel'
import type { AgentCompositeField } from '../types'
import {
  META as SUBTITLE_META,
  TRANSLATE_FIELDS,
  encodeTranslateToken,
  decodeTranslateToken,
} from './subtitle.meta'

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
  languageOptions?: SelectOption[]
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

// ── model store（新元件掛載必呼 ensureLoaded——沿批 2 既有慣例） ─────────────────
const modelStore = useModelStore()
onMounted(() => {
  modelStore.ensureLoaded()
})

// ══ Whisper picker（單欄 composite，token=variant；欄位名 model_size，非 whisper_model_size）═
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

const persistedWhisper = usePersistedModel('subtitle_whisper_model', '', { enabled: props.context === 'tool' })
const defaultWhisperToken = String(SUBTITLE_META.defaults().model_size ?? '')
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

// ── output_format（頂層 enum，沿舊 panel 靜態兩選項） ───────────────────────────
const outputFormatOptions = computed<SelectOption[]>(() => [
  { value: 'srt', label: t('video.subtitle.srt') },
  { value: 'vtt', label: t('video.subtitle.vtt') },
])
function onOutputFormatChange(v: string) {
  commitPatch({ output_format: v })
}

// ── source_language（選項由 prop 傳入；pipeline 語境無 prop 時退純文字輸入） ───────
function onSourceLanguageChange(v: string) {
  commitPatch({ source_language: v })
}
const hasLanguageOptions = computed(() => (props.languageOptions?.length ?? 0) > 0)

// ══ 翻譯區塊：內嵌 TranslationOptionsPanel（受控 modelValue）══════════════════════
// gate = target_language 非空字串（見 subtitle.meta.ts 檔頭註解，無獨立 enable_translation 欄位）。
const translationValue = computed<TranslationOptionsValue>(() => ({
  enable_translation: Boolean(props.params.target_language),
  target_language: String(props.params.target_language ?? ''),
  translate_model_token: encodeTranslateToken(props.params),
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
    // gate 關閉 → 清空全部 translate_* + keep_names/translate_style/glossary（undefined 覆蓋殘值,
    // 語意同 translate.meta.ts decodeModelToken 檔頭註解）。translate_remote 也明確清成
    // undefined（非 decodeTranslateToken('') 的 false）——gate 關閉時七欄應完全不殘留,
    // 而非留下一個「非 remote」的假訊號。
    commitPatch({
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
    target_language: v.target_language || 'zh-TW',
    keep_names: v.keep_names,
    translate_style: v.translate_style,
    glossary: parseGlossaryText(v.glossary_text),
    ...decodeTranslateToken(v.translate_model_token),
  })
}

// ── translate model picker options（供 composite agent 欄位讀取；TranslationOptionsPanel
// 額外 expose 的 translateModelOptions，經 template ref 讀取） ───────────────────────
const translationPanelRef = ref<{ translateModelOptions?: SelectItem[] } | null>(null)

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

// ── composite 註冊（whisper_model 單欄；translate_model 七欄——僅 gate 開啟才有意義，
// closed 時 get 回空字串,沿 brief 設計定案）。兩 host（SubtitlePanel 殼 / PipelineParamForm）
// 目前皆未 provide('registerComposite')（此 inject 僅 ToolParamHost.vue 提供），composite
// 目前無人消費——保留是為與批 2 其餘工具的 pattern 一致、為未來擴充預留（見 task report）。
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
  get: (p) => (p.target_language ? encodeTranslateToken(p) : ''),
  set: (token) => decodeTranslateToken(token),
})
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-badge-cc-fill me-2"></i>{{ $t('video.subtitle.title') }}
    </h6>

    <div class="form-group">
      <label>{{ $t('common.source_language') }}</label>
      <AppSelect
        v-if="hasLanguageOptions"
        :modelValue="String(params.source_language ?? '')"
        :options="languageOptions!"
        @update:modelValue="onSourceLanguageChange"
      />
      <input
        v-else
        type="text"
        class="form-input"
        :value="String(params.source_language ?? '')"
        :placeholder="$t('video.subtitle.source_language_placeholder')"
        @change="(e) => onSourceLanguageChange((e.target as HTMLInputElement).value)"
      />
    </div>

    <div class="form-group">
      <label>{{ $t('video.subtitle.model_settings') }}</label>
      <AppSelect
        :modelValue="whisperToken"
        :options="whisperModelOptions"
        :placeholder="$t('common.no_models_available')"
        @update:modelValue="onWhisperTokenChange"
      />
    </div>

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect
        :modelValue="String(params.output_format ?? 'srt')"
        :options="outputFormatOptions"
        @update:modelValue="onOutputFormatChange"
      />
    </div>

    <TranslationOptionsPanel
      ref="translationPanelRef"
      storage-key="subtitle_translate_model"
      :context="context"
      :model-value="translationValue"
      @update:model-value="onTranslationChange"
    />

    <SettingsCollapsible storage-key="video_subtitle_advanced">
      <div class="form-group">
        <AppToggle :modelValue="Boolean(params.vocal_separation)" @update:modelValue="onVocalSeparationChange">
          {{ $t('video.subtitle.vocal_separation') }}
        </AppToggle>
        <small class="form-hint">{{ $t('video.subtitle.vocal_separation_hint') }}</small>
      </div>

      <WhisperAdvancedSettings :embedded="true" :model-value="whisperAdvancedValue" @update:model-value="onWhisperAdvancedChange" />
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
