<script setup lang="ts">
/**
 * document.translate 參數元件（統一參數元件 spec §5／§6 Major 2；批 1 Task 1.5——
 * model picker composite agent 欄位「首用」打樣，UI 逐欄照搬舊
 * components/document/panels/DocumentTranslatePanel.vue（無 advanced 分組，全平鋪）。
 *
 * 核心 pattern：
 * - model picker 顯示值＝對 props.params 的響應式衍生（encodeModelToken），非獨立本地 state；
 *   使用者選擇 → decodeModelToken 產生七欄 patch → commitPatch 一次性 emit（one-shot，同
 *   TranscodeParams/CutParams 的 lastEmitted 回流判別）。
 * - glossary textarea 有「使用者輸入中」暫態，比照 CutParams 的 startText/endText：
 *   watch(props.params) 用 value-diff 對比上次自身 emit 的值，判別回流 vs 外部寫入。
 * - composite 註冊：inject('registerComposite')（由 ToolParamHost 提供；pipeline 語境的
 *   PipelineParamForm 未提供該 inject，register 為 undefined 時以 `register?.()` 跳過——
 *   picker 本身的 UI/emit 邏輯不依賴 composite 是否註冊成功，兩語境都能正常選模型）。
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import type { SelectItem, SelectOption } from '@/components/common/AppSelect.vue'
import { apiFetch } from '@/composables/useApi'
import { useModelStore } from '@/stores/models'
import { useRemoteModelStore } from '@/stores/remoteModels'
import { useModelOptions } from '@/composables/useModelOptions'
import { usePersistedModel } from '@/composables/usePersistedModel'
import type { AgentCompositeField } from '../types'
import { META as TRANSLATE_META, TRANSLATE_STYLES, encodeModelToken, decodeModelToken } from './translate.meta'

const { t } = useI18n()

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
}>()
const emit = defineEmits<{ 'update:params': [Record<string, unknown>] }>()

/** 鍵集合＋逐鍵 Object.is；用來判斷 watch 收到的 params 是否＝上次自己 emit 的值（回流） */
function shallowEqual(a: Record<string, unknown>, b: Record<string, unknown>): boolean {
  const ak = Object.keys(a)
  const bk = Object.keys(b)
  if (ak.length !== bk.length) return false
  return ak.every((k) => Object.is(a[k], b[k]))
}

let lastEmitted: Record<string, unknown> | null = null

function commit(next: Record<string, unknown>) {
  lastEmitted = next
  emit('update:params', next)
}

function commitPatch(patch: Record<string, unknown>) {
  commit({ ...props.params, ...patch })
}

// ── model picker（本地已裝＋雲端；沿舊 DocumentTranslatePanel 組裝邏輯搬入）───────
const modelStore = useModelStore()
const remoteStore = useRemoteModelStore()

// fresh session 掛載時模型清單可能尚未載入過（無人先觸發過 ensureLoaded）——舊
// DocumentTranslatePanel 與其他模型系 panel（VideoEnhancePanel/ImageOcrPanel 等）皆在
// onMounted 主動 ensureLoaded，否則 picker 會顯示空清單且 disabled（review finding #1
// 真機證據：fresh session picker 空，手動 ensureLoaded 後 55 模型才出現）。
onMounted(() => {
  modelStore.ensureLoaded()
  remoteStore.ensureLoaded()
})

const localModelOptions = computed<SelectOption[]>(() =>
  modelStore.forPanel(modelStore.byCapability('text'))
    .slice()
    .sort((a, b) => a.size_mb - b.size_mb)
    .map((m) => {
      const [size, quant] = m.variant.split(':')
      return {
        value: `${m.family}:${size}:${quant}`,
        label: m.label,
        badge: (m.downloaded ? 'ok' : 'err') as 'ok' | 'err',
      }
    }),
)

const { mergedOptions: modelOptions } = useModelOptions('text', localModelOptions)

function flattenTokens(items: SelectItem[]): string[] {
  return items.flatMap((o) => ('options' in o ? o.options.map((x) => x.value) : [o.value]))
}

const modelToken = computed(() => encodeModelToken(props.params))

function onModelTokenChange(token: string) {
  commitPatch(decodeModelToken(token))
  if (props.context === 'tool') persistedToken.value = token
}

// ── localStorage 持久化（Task 1.4 成果：enabled 依 context 開關；pipeline 語境不讀不寫）──
const persistedToken = usePersistedModel('doc_translate_model', '', { enabled: props.context === 'tool' })

// defaults 的 model token——seed guard 判準（fallback guard 改用 modelPickerSeeded 旗標，見下）。
const defaultModelToken = encodeModelToken(TRANSLATE_META.defaults())

// 順序 guard（review finding #4）：seed IIFE 與下面的 immediate fallback watch 都在 setup()
// 同一個同步 tick 跑完；commitPatch 的 emit 雖同步呼叫到 host 的 onParamsUpdate，但 host 更新
// params ref 後要「重新 render 傳新 prop 下來」是排程過的（Vue scheduler，非同步），所以 fallback
// watch 執行當下讀到的 props.params／modelToken.value 仍是 seed 套用前的舊值（reviewer 說的
// 「stale default token」）。若沿用「比對 modelToken 是否還等於 defaults」來判斷 fallback 該不
// 該跑，會因為讀到 stale 值而誤判成「還沒被動過」，於是 fallback 又用這份 stale props 算出
// 一次新 commitPatch——第二次 emit 蓋掉 host 對第一次 emit（seed）的處理結果，seed 選好的雲端
// 模型就在掛載瞬間被吃掉。改用不依賴 props 反應性的本地旗標：seed 一旦實際套用 patch，同步
// 標記旗標，fallback watch 讀旗標即可正確判斷「已經被動過」，不受 prop 更新排程延遲影響。
let modelPickerSeeded = false

// seed：僅在掛載時 params 仍等於 defaults（=使用者/host 尚未動過模型選擇）才套用持久化值——
// 用 model token 是否等於 defaults 的 token 判斷（比對後套 patch，沿 spec §5）。
{
  if (props.context === 'tool' && persistedToken.value && modelToken.value === defaultModelToken) {
    commitPatch(decodeModelToken(persistedToken.value))
    modelPickerSeeded = true
  }
}

// fallback：本地清單非同步載入後，若目前 token 未對應任何已知選項（本地或雲端）→
// 選第一個已下載的本地模型（鏡射舊 panel「避免 picker 顯示空白」的 immediate watch）。
// options.length===0 時直接跳過，不誤把「清單還沒載入」當成「token 無效」而清空選擇
// （舊 panel 曾有此 race——immediate watch 在 options 尚為空陣列時就把選擇重置為空字串）。
// modelPickerSeeded 為 true（persisted seed 剛套用過）時整段跳過，見上方旗標註解。
watch(
  localModelOptions,
  (options) => {
    if (modelPickerSeeded) return
    if (options.length === 0) return
    if (flattenTokens(modelOptions.value).includes(modelToken.value)) return
    const first = options.find((o) => o.badge === 'ok')
    if (first) {
      onModelTokenChange(first.value)
      modelPickerSeeded = true
    }
  },
  { immediate: true },
)

// ── 語言 ──────────────────────────────────────────────────────────────────
const languageOptions = ref<{ value: string; label: string }[]>([])

async function loadLanguages() {
  try {
    const res = await apiFetch('/llm/translate/languages')
    if (res.ok) {
      const data = await res.json() as { code: string; name: string }[]
      languageOptions.value = data.map((l) => ({ value: l.code, label: l.name }))
    }
  } catch { /* 沿舊 panel：載入失敗靜默，清單維持空 */ }
}
loadLanguages()

// ── 翻譯風格 ──────────────────────────────────────────────────────────────
const styleI18nKey: Record<string, string> = {
  colloquial: 'common.translate_style_colloquial',
  formal: 'common.translate_style_formal',
  literal: 'common.translate_style_literal',
}
const styleOptions = computed(() =>
  TRANSLATE_STYLES.map((v) => ({ value: v, label: t(styleI18nKey[v] ?? v) })),
)

// ── 專有名詞字典（glossary textarea ↔ dict；沿舊 panel 解析邏輯，含非法行容錯）─────
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

const glossaryText = ref(glossaryToText(props.params.glossary))

watch(
  () => props.params,
  (p) => {
    // one-shot：watch 一觸發就消費 lastEmitted，無論此次是回流還是外部寫入，永不 stale
    const echo = lastEmitted
    lastEmitted = null
    if (echo && shallowEqual(p, echo)) return
    glossaryText.value = glossaryToText(p.glossary)
  },
  { deep: true },
)

function commitGlossary() {
  commitPatch({ glossary: parseGlossaryText(glossaryText.value) })
}

// ── 其餘欄位 commit ─────────────────────────────────────────────────────────
function onSourceLanguageChange(v: string) {
  commitPatch({ source_language: v })
}
function onTargetLanguageChange(v: string) {
  commitPatch({ target_language: v })
}
function onStyleChange(v: string) {
  commitPatch({ translate_style: v })
}

// ── composite 註冊（model picker 覆蓋七個後端欄位，曝給 agent 單一 'translate_model' 欄位）──
const registerComposite = inject<(c: AgentCompositeField) => () => void>('registerComposite')
registerComposite?.({
  name: 'translate_model',
  covers: ['model_family', 'model_size', 'quantization', 'remote', 'provider', 'conn_id', 'remote_model'],
  options: () => flattenTokens(modelOptions.value),
  get: (p) => encodeModelToken(p),
  set: (token) => decodeModelToken(token),
})
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-translate me-2"></i>{{ $t('document.translate.title') }}
    </h6>
    <p class="form-hint">{{ $t('document.translate.description') }}</p>

    <!-- 翻譯模型 -->
    <div class="form-group">
      <label>{{ $t('document.translate.model') }}</label>
      <AppSelect :modelValue="modelToken" :options="modelOptions" @update:modelValue="onModelTokenChange" />
    </div>

    <!-- 來源語言 -->
    <div class="form-group">
      <label>{{ $t('common.source_language') }}</label>
      <AppSelect
        :modelValue="String(params.source_language ?? '')"
        :options="languageOptions"
        @update:modelValue="onSourceLanguageChange"
      />
    </div>

    <!-- 目標語言 -->
    <div class="form-group">
      <label>{{ $t('common.target_language') }}</label>
      <AppSelect
        :modelValue="String(params.target_language ?? '')"
        :options="languageOptions"
        @update:modelValue="onTargetLanguageChange"
      />
    </div>

    <!-- 翻譯風格 -->
    <div class="form-group">
      <label>{{ $t('document.translate.style') }}</label>
      <AppSelect
        :modelValue="String(params.translate_style ?? 'colloquial')"
        :options="styleOptions"
        @update:modelValue="onStyleChange"
      />
    </div>

    <!-- 專有名詞字典 -->
    <div class="form-group">
      <label>{{ $t('document.translate.glossary') }} <span class="label-hint">{{ $t('document.translate.optional') }}</span></label>
      <textarea
        v-model="glossaryText"
        class="form-input glossary-input"
        :placeholder="$t('document.translate.glossary_format')"
        rows="4"
        @change="commitGlossary"
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
