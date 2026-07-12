<script setup lang="ts">
/**
 * audio.lyrics 參數元件（統一參數元件 spec §5；批 3 Task 3.5——批 3 收官，照 TranscribeParams.vue
 * 裁剪：lyrics 是 transcribe 的子集，見 lyrics.meta.ts 檔頭「與 audio.transcribe 的關鍵差異」）。
 * UI 沿舊 components/audio/panels/AudioLyricsPanel.vue：model/output_format 兩個 top-level
 * form-group；TranslationOptionsPanel（內嵌、受控 v-model）top-level（非 SettingsCollapsible，
 * 同舊 panel）；align 進 SettingsCollapsible 進階區（沿佈局鐵則——舊 panel SettingsCollapsible
 * 範圍僅此一欄）。**無 vocal_separation UI、無 WhisperAdvancedSettings、無 summarize**（皆
 * transcribe 獨有，見 meta 檔頭差異 2/3）；**無 source_language**（後端沒有這欄位）。
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import type { SelectItem, SelectOption } from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import TranslationOptionsPanel, { type TranslationOptionsValue } from '@/components/video/TranslationOptionsPanel.vue'
import { useModelStore } from '@/stores/models'
import { useRemoteModelStore } from '@/stores/remoteModels'
import { usePersistedModel } from '@/composables/usePersistedModel'
import type { AgentCompositeField } from '../types'
import {
  META as LYRICS_META,
  TRANSLATE_FIELDS,
  encodeTranslateToken,
  decodeTranslateToken,
} from './lyrics.meta'

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

const persistedWhisper = usePersistedModel('lyrics_whisper_model', '', { enabled: props.context === 'tool' })
const defaultWhisperToken = String(LYRICS_META.defaults().model_size ?? '')
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

// ── output_format（頂層 enum，lrc/txt） ──────────────────────────────────────
const outputFormatOptions = computed<SelectOption[]>(() => [
  { value: 'lrc', label: t('audio.lyrics.lrc') },
  { value: 'txt', label: t('audio.lyrics.txt') },
])
function onOutputFormatChange(v: string) {
  commitPatch({ output_format: v })
}

// ══ 翻譯區塊：內嵌 TranslationOptionsPanel（受控 modelValue）══════════════════════
// gate = params.translate（獨立 bool 欄位，同 transcribe，非 subtitle 的 target_language 非空判準）。
const translationValue = computed<TranslationOptionsValue>(() => ({
  enable_translation: props.params.translate === true,
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
    // gate 關閉 → translate 明確寫 false + 清空全部 translate_* + keep_names/translate_style/
    // glossary（undefined 覆蓋殘值，語意同 transcribe/subtitle.meta.ts decodeTranslateToken 註解）。
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
    ...decodeTranslateToken(v.translate_model_token),
  })
}

// translate model picker options（供 composite agent 欄位讀取；TranslationOptionsPanel 額外
// expose 的 translateModelOptions，經 template ref 讀取，同 TranscribeParams.vue pattern）。
const translationPanelRef = ref<{ translateModelOptions?: SelectItem[] } | null>(null)

// ══ align（advanced，SettingsCollapsible，v-model 化） ═══════════════════════════
function onAlignChange(v: boolean) {
  commitPatch({ align: v })
}

// ── composite 註冊（whisper_model 單欄；translate_model 七欄） ────────────────────
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
  get: (p) => (p.translate === true ? encodeTranslateToken(p) : ''),
  set: (token) => decodeTranslateToken(token),
})
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-music-note-list me-2"></i>{{ $t('audio.lyrics.title') }}
    </h6>
    <p class="form-hint">{{ $t('audio.lyrics.description') }}</p>

    <div class="form-group">
      <label>{{ $t('audio.lyrics.model') }}</label>
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
        :modelValue="String(params.output_format ?? 'lrc')"
        :options="outputFormatOptions"
        @update:modelValue="onOutputFormatChange"
      />
    </div>

    <TranslationOptionsPanel
      ref="translationPanelRef"
      storage-key="audio_lyrics_translate_model"
      :context="context"
      :model-value="translationValue"
      @update:model-value="onTranslationChange"
    />

    <SettingsCollapsible storage-key="audio_lyrics_advanced">
      <div class="form-group">
        <AppToggle :modelValue="Boolean(params.align)" @update:modelValue="onAlignChange">
          {{ $t('audio.lyrics.align') }}
        </AppToggle>
        <small class="form-hint">{{ $t('audio.lyrics.align_hint') }}</small>
      </div>
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
