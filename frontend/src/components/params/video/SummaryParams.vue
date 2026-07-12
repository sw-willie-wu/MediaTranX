<script setup lang="ts">
/**
 * video.summary 參數元件（統一參數元件 spec §5；批 2 Task 2.4——批 2 最大工具）。
 * UI 沿舊 components/video/panels/VideoSummaryPanel.vue：summary_mode/whisper picker/
 * llm picker/vlm picker 皆頂層；vocal_separation＋WhisperAdvancedSettings 進 SettingsCollapsible
 * 進階區；language 欄位舊 panel 無 UI（恆用 props.language 預設 'zh-TW'）——佈局鐵則新欄位
 * 進進階區（見 summary.meta.ts 檔頭）。
 *
 * 三個 model picker：
 * - whisper_model：單欄 composite（token=variant），同 InterpolateParams pattern。
 * - llm_model / vlm_model：六欄 composite（token=encodeModelToken/decodeModelToken，family:size
 *   或 remote:provider:connId:modelId），同 TranslateParams pattern，唯無 quantization 段。
 *   VLM 多一個 ''（不使用）哨兵選項，prepend 進 merged options 最前面。
 *
 * 三個 picker 的 seed/auto-select 均沿 TranslateParams.vue 的 modelPickerSeeded flag pattern
 * （非舊 VideoSummaryPanel 的無旗標「每次 options 變動都重新校正」寫法——批 1 Task 1.5 review
 * 已定案：composite commitPatch 的 emit 不同步反映到 props（Vue 排程），若每次 options 變動都
 * 無條件重算，會與 seed IIFE 在同一 tick 內互踩，見 TranslateParams.vue 檔頭「順序 guard」註解）。
 * 三個 picker 的 seed/auto-select 皆只在 context==='tool' 執行（brief 設計定案；pipeline 節點
 * 不做 localStorage seed，也不做「避免空白選擇」的自動校正——沿 spec seedOnFileChange/
 * usePersistedModel enabled 語意，pipeline 節點的初值僅來自 meta.defaults()/recipe）。
 */
import { computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import type { SelectItem, SelectOption } from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import WhisperAdvancedSettings, { type WhisperAdvancedValue } from '@/components/video/WhisperAdvancedSettings.vue'
import { useModelStore } from '@/stores/models'
import { useRemoteModelStore } from '@/stores/remoteModels'
import { useModelOptions } from '@/composables/useModelOptions'
import { usePersistedModel } from '@/composables/usePersistedModel'
import { useRegisterComposite } from '@/composables/useRegisterComposite'
import {
  META as SUMMARY_META,
  SUMMARY_MODES,
  LLM_FIELDS,
  VLM_FIELDS,
  encodeModelToken,
  decodeModelToken,
} from './summary.meta'

const { t } = useI18n()

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
}>()
const emit = defineEmits<{ 'update:params': [Record<string, unknown>] }>()

function commit(next: Record<string, unknown>) {
  emit('update:params', next)
}
function commitPatch(patch: Record<string, unknown>) {
  commit({ ...props.params, ...patch })
}

function flattenTokens(items: SelectItem[]): string[] {
  return items.flatMap((o) => ('options' in o ? o.options.map((x) => x.value) : [o.value]))
}

// ── model stores（fresh session 掛載時清單可能尚未載入——沿 TranslateParams/InterpolateParams
// 既有慣例，onMounted 主動 ensureLoaded） ─────────────────────────────────────
const modelStore = useModelStore()
const remoteStore = useRemoteModelStore()

onMounted(() => {
  modelStore.ensureLoaded()
  remoteStore.ensureLoaded()
})

// ══ Whisper picker（單欄 composite，token=variant）══════════════════════════
const whisperModelOptions = computed<SelectOption[]>(() =>
  modelStore.forPanel(modelStore.byCategory('stt')).map((m) => ({
    value: m.variant,
    label: m.label,
    badge: (m.downloaded ? 'ok' : 'err') as 'ok' | 'err',
  })),
)

const whisperToken = computed(() => String(props.params.whisper_model_size ?? ''))

function onWhisperTokenChange(token: string) {
  commitPatch({ whisper_model_size: token })
  if (props.context === 'tool') persistedWhisper.value = token
}

// fallback 用空字串（非 schema default 'medium'）——若 fallback 與 default 相同，「從未持久化過」
// 與「persisted 值恰好等於 default」在 seed IIFE 眼中會無法區分，導致 whisperSeeded 在完全沒有
// localStorage 殘留值時也被誤標 true，永久封鎖下面的 fallback watch（同 llm/vlm/TranslateParams
// 既有慣例：fallback 恆用 ''，UI 顯示值另由 props.params 衍生，不受此 fallback 影響）。
const persistedWhisper = usePersistedModel('video_summary_whisper_model', '', { enabled: props.context === 'tool' })
const defaultWhisperToken = String(SUMMARY_META.defaults().whisper_model_size ?? '')
let whisperSeeded = false

// ══ 四個 setup 期同步 seed（whisper/llm/vlm/summary_mode）收斂成單次 commitPatch（IMP-1 修復）══
// 問題：每個 commitPatch 都是 `{...props.params, ...patch}`，而 props.params 在同一個同步
// tick 內不會因為前一個 emit 而更新（Vue prop 回流要等父層下一輪 render/flush，非同步）。
// 若四段各自呼叫 commitPatch，後面的一定基於「還沒套用前面 patch」的 stale props.params，
// 導致後 seed 覆蓋前 seed（例：使用者 localStorage 同時存有 whisper 與 llm 模型時，掛載後
// llm 的 patch 會把 whisper 剛寫入的欄位悄悄復原）。summary_mode 的 seed 額外有「fallback
// 與 default 皆為 'bullets'」的巧合——只要 tool context 掛載時 params.summary_mode 已是
// 'bullets'（ToolParamHost 初始值即 meta.defaults()，天生如此），這段 IIFE 幾乎每次掛載都會
// 觸發，若不併入同一顆 seed，會在其餘三個 model picker 之後把它們的 patch 整批覆蓋掉，
// 使本次修復對 SummaryParams 名不副實——故一併收斂，不僅限 review 原列的三個 model picker。
// 修法：四段各自只把要寫的欄位塞進共用 `seed` 物件，seeded flag 語意不變（仍只在
// context==='tool' 且 persisted 有值時設 true，供各自 fallback watch 判斷是否跳過)，最後
// 一次性 `if (Object.keys(seed).length) commitPatch(seed)`（見 summary_mode 段落後方）。
const seed: Record<string, unknown> = {}

if (props.context === 'tool' && persistedWhisper.value && whisperToken.value === defaultWhisperToken) {
  seed.whisper_model_size = persistedWhisper.value
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

// ══ LLM picker（六欄 composite，本地 family:size 或 remote 四段）══════════════
function buildLocalOptions(capability: string): SelectOption[] {
  const seen = new Map<string, { value: string; label: string; downloaded: boolean }>()
  for (const m of modelStore.forPanel(modelStore.byCapability(capability))) {
    const [size] = m.variant.split(':')
    const key = `${m.family}:${size}`
    if (!seen.has(key)) {
      const labelNoQuant = m.label.split(' ').slice(0, -1).join(' ')
      seen.set(key, { value: key, label: labelNoQuant, downloaded: m.downloaded })
    } else if (m.downloaded) {
      seen.get(key)!.downloaded = true
    }
  }
  return [...seen.values()].map((opt) => ({
    value: opt.value,
    label: opt.label,
    badge: (opt.downloaded ? 'ok' : 'err') as 'ok' | 'err',
  }))
}

const localLlmOptions = computed<SelectOption[]>(() => buildLocalOptions('text'))
const { mergedOptions: llmOptions } = useModelOptions('text', localLlmOptions, { providers: ['ollama', 'openai', 'gemini'] })

const llmToken = computed(() => encodeModelToken(props.params, 'llm'))

function onLlmTokenChange(token: string) {
  commitPatch(decodeModelToken(token, 'llm'))
  if (props.context === 'tool') persistedLlm.value = token
}

const persistedLlm = usePersistedModel('video_summary_llm_model', '', { enabled: props.context === 'tool' })
const defaultLlmToken = encodeModelToken(SUMMARY_META.defaults(), 'llm')
let llmSeeded = false

if (props.context === 'tool' && persistedLlm.value && llmToken.value === defaultLlmToken) {
  Object.assign(seed, decodeModelToken(persistedLlm.value, 'llm'))
  llmSeeded = true
}

watch(
  localLlmOptions,
  (options) => {
    if (props.context !== 'tool') return
    if (llmSeeded) return
    if (options.length === 0) return
    if (flattenTokens(llmOptions.value).includes(llmToken.value)) return
    const first = options.find((o) => o.badge === 'ok')
    if (first) {
      onLlmTokenChange(first.value)
      llmSeeded = true
    }
  },
  { immediate: true },
)

// ══ VLM picker（同 LLM，多一個 ''（不使用）哨兵選項）══════════════════════════
const localVlmOptions = computed<SelectOption[]>(() => buildLocalOptions('vision'))
const { mergedOptions: vlmOptionsBase } = useModelOptions('vision', localVlmOptions, { providers: ['ollama', 'openai', 'gemini'] })
const vlmOptions = computed<SelectItem[]>(() => [
  { value: '', label: t('video.summary.vlm_none') },
  ...vlmOptionsBase.value,
])

const vlmToken = computed(() => encodeModelToken(props.params, 'vlm'))

function onVlmTokenChange(token: string) {
  commitPatch(decodeModelToken(token, 'vlm'))
  if (props.context === 'tool') persistedVlm.value = token
}

const persistedVlm = usePersistedModel('video_summary_vlm_model', '', { enabled: props.context === 'tool' })
const defaultVlmToken = encodeModelToken(SUMMARY_META.defaults(), 'vlm')
let vlmSeeded = false

if (props.context === 'tool' && persistedVlm.value && vlmToken.value === defaultVlmToken) {
  Object.assign(seed, decodeModelToken(persistedVlm.value, 'vlm'))
  vlmSeeded = true
}

// 沿 LLM 同構寫法保留 fallback watch——'' 哨兵值恆存在於 vlmOptions，故
// flattenTokens(...).includes(vlmToken.value) 在預設空狀態下恆為 true，此 watch 實際
// 不會自動選中任何具體模型（VLM 選配、留空即「不使用」，沿舊 VideoSummaryPanel 無
// 獨立 VLM auto-select watch 的既有行為——見 summary.meta.ts/task report 說明）。
watch(
  localVlmOptions,
  (options) => {
    if (props.context !== 'tool') return
    if (vlmSeeded) return
    if (options.length === 0) return
    if (flattenTokens(vlmOptions.value).includes(vlmToken.value)) return
    const first = options.find((o) => o.badge === 'ok')
    if (first) {
      onVlmTokenChange(first.value)
      vlmSeeded = true
    }
  },
  { immediate: true },
)

// ══ summary_mode（非 model composite，plain enum 欄位，仍走 usePersistedModel 持久化）══
const modeOptions = computed(() =>
  SUMMARY_MODES.map((v) => ({ value: v, label: t(v === 'bullets' ? 'video.summary.mode_bullets' : 'video.summary.mode_narrative') })),
)

const persistedMode = usePersistedModel('video_summary_mode', 'bullets', { enabled: props.context === 'tool' })
const defaultMode = String(SUMMARY_META.defaults().summary_mode ?? 'bullets')

if (props.context === 'tool' && persistedMode.value && String(props.params.summary_mode ?? '') === defaultMode) {
  seed.summary_mode = persistedMode.value
}

// 四段 seed 蒐集完畢，單次提交（見上方 whisper 段落註解——IMP-1 修復核心）。
if (Object.keys(seed).length) commitPatch(seed)

function onModeChange(v: string) {
  commitPatch({ summary_mode: v })
  if (props.context === 'tool') persistedMode.value = v
}

// ══ vocal_separation / WhisperAdvancedSettings（v-model 化，見該元件檔頭註解）══════════
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

// ── language（新欄位，舊 panel 無 UI——佈局鐵則進進階區；純文字輸入，無 dynamic 清單） ──
function onLanguageChange(v: string) {
  commitPatch({ language: v })
}

// ── composite 註冊（whisper_model 單欄；llm_model/vlm_model 六欄，皆覆蓋後端欄位群） ────
const registerComposite = useRegisterComposite()
registerComposite?.({
  name: 'whisper_model',
  covers: ['whisper_model_size'],
  options: () => whisperModelOptions.value.map((o) => o.value),
  get: (p) => String(p.whisper_model_size ?? ''),
  set: (token) => ({ whisper_model_size: token }),
})
registerComposite?.({
  name: 'llm_model',
  covers: [...LLM_FIELDS],
  options: () => flattenTokens(llmOptions.value),
  get: (p) => encodeModelToken(p, 'llm'),
  set: (token) => decodeModelToken(token, 'llm'),
})
registerComposite?.({
  name: 'vlm_model',
  covers: [...VLM_FIELDS],
  options: () => flattenTokens(vlmOptions.value),
  get: (p) => encodeModelToken(p, 'vlm'),
  set: (token) => decodeModelToken(token, 'vlm'),
})
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-card-text me-2"></i>{{ $t('video.summary.title') }}
    </h6>
    <p class="form-hint">{{ $t('video.summary.description') }}</p>

    <div class="form-group">
      <label>{{ $t('video.summary.mode') }}</label>
      <AppSelect :modelValue="String(params.summary_mode ?? 'bullets')" :options="modeOptions" @update:modelValue="onModeChange" />
    </div>

    <div class="form-group">
      <label>{{ $t('video.summary.whisper_model') }}</label>
      <AppSelect
        :modelValue="whisperToken"
        :options="whisperModelOptions"
        :placeholder="$t('common.no_models_available')"
        @update:modelValue="onWhisperTokenChange"
      />
    </div>

    <div class="form-group">
      <label>{{ $t('video.summary.llm_model') }}</label>
      <AppSelect :modelValue="llmToken" :options="llmOptions" :placeholder="$t('video.summary.select_model')" @update:modelValue="onLlmTokenChange" />
      <small class="form-hint">{{ $t('video.summary.llm_model_hint') }}</small>
    </div>

    <div class="form-group">
      <label>{{ $t('video.summary.vlm_model') }}</label>
      <AppSelect :modelValue="vlmToken" :options="vlmOptions" @update:modelValue="onVlmTokenChange" />
      <small class="form-hint">{{ $t('video.summary.vlm_model_hint') }}</small>
    </div>

    <SettingsCollapsible storage-key="video_summary_advanced">
      <div class="form-group">
        <label>{{ $t('video.summary.language') }}</label>
        <input
          type="text"
          class="form-input"
          :value="String(params.language ?? 'zh-TW')"
          @change="(e) => onLanguageChange((e.target as HTMLInputElement).value)"
        />
        <small class="form-hint">{{ $t('video.summary.language_hint') }}</small>
      </div>

      <div class="form-group">
        <AppToggle :modelValue="Boolean(params.vocal_separation)" @update:modelValue="onVocalSeparationChange">
          {{ $t('video.summary.vocal_separation') }}
        </AppToggle>
        <small class="form-hint">{{ $t('video.summary.vocal_separation_hint') }}</small>
      </div>

      <WhisperAdvancedSettings :embedded="true" :model-value="whisperAdvancedValue" @update:model-value="onWhisperAdvancedChange" />
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
