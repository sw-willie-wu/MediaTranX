<script setup lang="ts">
/**
 * document.ocr／image.ocr 共用參數元件（統一參數元件 spec §5；批 4 Task 4.4）。
 * 兩個舊 panel（DocumentOcrPanel.vue／ImageOcrPanel.vue）逐行比對後欄位/邏輯完全相同——
 * PARAM_COMPONENTS['document.ocr'] 與 PARAM_COMPONENTS['image.ocr'] 都指到本檔（見
 * params/index.ts），各自 META 見 document/ocr.meta.ts／image/ocr.meta.ts。
 *
 * 隨掛載點變化的兩處差異透過 fallthrough attrs 傳入（沿 FilterParams.vue 的 fieldGroup
 * 先例——ToolParamHost 未宣告的 prop 會自動落到 $attrs、轉發到本元件）：
 * - persistKey：localStorage 持久化鍵，沿用舊字面值 'doc_ocr_model'／'image_ocr_model'
 *   （不可用機械規則從 toolKey 推導——'document'≠'doc' 縮寫，必須保留舊鍵以相容既有使用者
 *   的已存偏好，不能悄悄重置）。
 * - i18nPrefix：i18n key 前綴（'document.ocr'／'image.ocr'），衍生出 title/description/model/
 *   markdown/text 五把 key；兩域既有 i18n 詞條各自獨立（未合併），故用前綴參數化而非改動
 *   詞條本身。
 * pipeline context 兩者皆不傳（PipelineParamForm 掛載時無 fallthrough）——這兩個 prop 只影響
 * localStorage 持久化與顯示文案，pipeline 語境下 persist 本就 disabled（enabled:
 * context==='tool'），i18nPrefix 預設落 'document.ocr' 純粹是文案顯示，不影響提交邏輯。
 *
 * 已刻意不遷移的舊行為：兩隻舊 panel 各自的 `GET .../ocr/status` 前置探測與
 * 「找不到 server」info-box——見 document/ocr.meta.ts 檔頭「⚠ 兩隻舊 panel 皆有額外一道」
 * 段落，決策理由與全案模型系工具一致性有關,非本檔遺漏。
 *
 * isPdfOrImage（document 專屬的副檔名 disabled 判斷）刻意不進本元件——validate 只吃
 * params 做不到，副檔名判斷留在 View 層（DocumentView.vue 的 executeDisabled 計算式
 * 另外 `|| !isPdfOrImage`），見該檔與 batch4-recon.md §9 document.ocr 節。
 */
import { computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import type { SelectItem } from '@/components/common/AppSelect.vue'
import { useModelStore } from '@/stores/models'
import { useRemoteModelStore } from '@/stores/remoteModels'
import { useModelOptions } from '@/composables/useModelOptions'
import { usePersistedModel } from '@/composables/usePersistedModel'
import { useRegisterComposite } from '@/composables/useRegisterComposite'
import { encodeModelToken, decodeModelToken, buildOcrMeta } from './ocr.meta'

const { t } = useI18n()

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
  /** localStorage 持久化鍵（見檔頭註解）；未傳時退回 'doc_ocr_model'（僅 pipeline 語境會發生，無害）。 */
  persistKey?: string
  /** i18n key 前綴（見檔頭註解）；未傳時退回 'document.ocr'。 */
  i18nPrefix?: string
}>()
const emit = defineEmits<{ 'update:params': [Record<string, unknown>] }>()

function commit(next: Record<string, unknown>) {
  emit('update:params', next)
}
function commitPatch(patch: Record<string, unknown>) {
  commit({ ...props.params, ...patch })
}

const prefix = computed(() => props.i18nPrefix ?? 'document.ocr')

// ── 模型 picker（本地已裝＋雲端；沿舊 Document/ImageOcrPanel 組裝邏輯搬入）───────────
const modelStore = useModelStore()
const remoteStore = useRemoteModelStore()
const persistKey = props.persistKey ?? 'doc_ocr_model'

onMounted(() => {
  modelStore.ensureLoaded()
  remoteStore.ensureLoaded()
})

const localModelOptions = computed(() => {
  const seen = new Map<string, { value: string; label: string; downloaded: boolean }>()
  for (const m of modelStore.forPanel(modelStore.byCapability('vision'))) {
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
    ...opt,
    badge: opt.downloaded ? ('ok' as const) : ('err' as const),
  }))
})

const { mergedOptions: modelOptions } = useModelOptions('vision', localModelOptions)

function flattenTokens(items: SelectItem[]): string[] {
  return items.flatMap((o) => ('options' in o ? o.options.map((x) => x.value) : [o.value]))
}

const modelToken = computed(() => encodeModelToken(props.params))

function onModelTokenChange(token: string) {
  commitPatch(decodeModelToken(token))
  if (props.context === 'tool') persistedToken.value = token
}

const persistedToken = usePersistedModel(persistKey, '', { enabled: props.context === 'tool' })

// defaults 的 model token——seed guard 判準（沿 TranslateParams.vue pattern；toolKey 對
// seed 判準無影響，用一個中性的暫時 META 取 defaults()）。
const defaultModelToken = encodeModelToken(
  buildOcrMeta({ toolKey: '', apiPath: '', labelKey: '', taskType: '', agentExecuteLabel: '' }).defaults(),
)

let modelPickerSeeded = false

// seed：僅在掛載時 params 仍等於 defaults（=使用者/host 尚未動過模型選擇）才套用持久化值。
{
  if (props.context === 'tool' && persistedToken.value && modelToken.value === defaultModelToken) {
    commitPatch(decodeModelToken(persistedToken.value))
    modelPickerSeeded = true
  }
}

// fallback：本地清單非同步載入後，若目前 token 未對應任何已知選項（本地或雲端）→
// 選第一個已下載的本地模型（鏡射舊 panel「避免 picker 顯示空白」的 immediate watch）。
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

// ── 輸出格式 ──────────────────────────────────────────────────────────────
const outputFormatOptions = computed(() => [
  { value: 'md', label: t(`${prefix.value}.markdown`) },
  { value: 'txt', label: t(`${prefix.value}.text`) },
])

function onOutputFormatChange(v: string) {
  commitPatch({ output_format: v })
}

// ── composite 註冊（model picker 覆蓋七個後端欄位；agent 欄位名沿舊兩隻 panel 皆用 'model'）──
const registerComposite = useRegisterComposite()
registerComposite?.({
  name: 'model',
  covers: ['model_family', 'model_size', 'quantization', 'remote', 'provider', 'conn_id', 'remote_model'],
  options: () => flattenTokens(modelOptions.value),
  get: (p) => encodeModelToken(p),
  set: (token) => decodeModelToken(token),
})
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-type me-2"></i>{{ $t(`${prefix}.title`) }}</h6>
    <p class="form-hint">{{ $t(`${prefix}.description`) }}</p>

    <div class="form-group">
      <label>{{ $t(`${prefix}.model`) }}</label>
      <AppSelect :modelValue="modelToken" :options="modelOptions" @update:modelValue="onModelTokenChange" />
    </div>

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect
        :modelValue="String(params.output_format ?? 'md')"
        :options="outputFormatOptions"
        @update:modelValue="onOutputFormatChange"
      />
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
