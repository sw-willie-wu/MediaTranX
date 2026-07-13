<script setup lang="ts">
/**
 * video.download 參數元件（統一參數元件 spec §5；批 2 Task 2.2）。
 * pipeline-only source 節點：只由 PipelineParamForm 掛載（context 恆為 'pipeline'）——
 * 工具頁的下載走全域彈窗 UrlDownloadCard.vue（App.vue 根層），與本元件無關。
 * 契約：params/context/fileInfo in、update:params out——host 統一收發，本元件不呼叫 API。
 *
 * 核心 pattern 沿 CutParams/CropParams：url/title 文字欄用本地 ref 緩衝＋one-shot
 * lastEmitted value-diff（使用者輸入中不被外部回流打斷）；mode/max_height 是對
 * format_intent dict 的衍生 UI，一律整顆 format_intent 新物件 one-shot emit。
 * shallowEqual 沿用 CutParams 的淺層 Object.is 假設——format_intent 是巢狀物件，
 * 每次編輯都會產生新的物件參考，watch 收到回流時 shallowEqual 對 format_intent 這鍵
 * 幾乎必判「不同」（框架的 reactive() 深層代理也會讓參考不同），因此每次 format_intent
 * 相關的 commit 之後，watch 觸發都會連帶重推一次 url/title 顯示字串——這是「多餘重推」
 * 而非資料錯誤（重推的目標值與目前顯示值相同，看不出差異），採用 brief 建議的安全方向
 * （接受多餘重推，不做深比較），保持與其他 25 個元件一致的簡單實作。
 *
 * legacy 相容：批 2 前 registry 的 video.download paramSchema 把 format_intent 誤建成
 * scalar enum（'auto'|'video'|'audio'），舊 recipe 可能存過這種字串值；也可能存在
 * 完全沒有 format_intent 鍵的舊節點。掛載時偵測到這兩種情形，一次性 emit 正規化成
 * {mode:'auto'}，把壞資料寫回 host／pipeline store（不只是顯示層防禦——不修正的話，
 * 使用者若不動 mode/max_height/title，儲存/執行 recipe 時後端仍會收到壞值 → 422）。
 * mode/max_height 的顯示衍生（formatIntent computed）另外對任何非物件形狀（含 null/
 * array）都防禦性 fallback 成 {mode:'auto'}，涵蓋掛載到 emit 回流之間的過渡瞬間。
 *
 * mode 選項標籤重用既有 video_download.quality_auto/cap/ask（設定頁
 * SettingsVideoDownload.vue 的下載畫質三選項——語意與後端 FormatIntent.mode /
 * VideoDownloadSettings.quality_mode 完全相同的 Literal['auto','cap','ask']），
 * 避免新增重複翻譯內容。
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import type { SelectOption } from '@/components/common/AppSelect.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
}>()
const emit = defineEmits<{ 'update:params': [Record<string, unknown>] }>()

const { t } = useI18n()

/** 鍵集合＋逐鍵 Object.is；用來判斷 watch 收到的 params 是否＝上次自己 emit 的值（回流）。
 *  假設 params 為淺層 primitive；format_intent 是物件值——見檔頭註記，接受多餘重推。 */
function shallowEqual(a: Record<string, unknown>, b: Record<string, unknown>): boolean {
  const ak = Object.keys(a)
  const bk = Object.keys(b)
  if (ak.length !== bk.length) return false
  return ak.every((k) => Object.is(a[k], b[k]))
}

function isPlainDict(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function numOrNull(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

/** 顯示/編輯用的 format_intent 衍生值：任何非物件形狀一律防禦性 fallback，
 *  涵蓋掛載到下方正規化 emit 回流之間的過渡瞬間（不會讓 UI 讀到 'auto' 字串本身炸掉）。 */
const formatIntent = computed<Record<string, unknown>>(() =>
  isPlainDict(props.params.format_intent) ? props.params.format_intent : { mode: 'auto' },
)

const urlText = ref(String(props.params.url ?? ''))
const titleText = ref(String(props.params.title ?? 'video'))
const maxHeightLocal = ref<number | null>(numOrNull(formatIntent.value.max_height))

let lastEmitted: Record<string, unknown> | null = null

watch(
  () => props.params,
  (p) => {
    // one-shot：watch 一觸發就消費 lastEmitted，無論此次是回流還是外部寫入，永不 stale
    const echo = lastEmitted
    lastEmitted = null
    if (echo && shallowEqual(p, echo)) return
    urlText.value = String(p.url ?? '')
    titleText.value = String(p.title ?? 'video')
    const fi = isPlainDict(p.format_intent) ? p.format_intent : { mode: 'auto' }
    maxHeightLocal.value = numOrNull(fi.max_height)
  },
  { deep: true },
)

function commit(next: Record<string, unknown>) {
  lastEmitted = next
  emit('update:params', next)
}

function commitUrl() {
  commit({ ...props.params, url: urlText.value })
}

function commitTitle() {
  commit({ ...props.params, title: titleText.value })
}

function onModeChange(v: string) {
  commit({ ...props.params, format_intent: { ...formatIntent.value, mode: v } })
}

function commitMaxHeight() {
  const next = { ...formatIntent.value }
  const n = numOrNull(maxHeightLocal.value)
  if (n === null) {
    delete next.max_height
  } else {
    next.max_height = n
  }
  commit({ ...props.params, format_intent: next })
}

// ── legacy 相容：掛載時若 format_intent 是字串（舊 scalar 建模）或 undefined（舊節點
// 未存過此鍵），一次性正規化成 {mode:'auto'} 並 emit（見檔頭註記）。合法 dict 不動。 ──
{
  const raw = props.params.format_intent
  if (typeof raw === 'string' || raw === undefined) {
    commit({ ...props.params, format_intent: { mode: 'auto' } })
  }
}

const modeOptions = computed<SelectOption[]>(() => [
  { value: 'auto', label: t('video_download.quality_auto') },
  { value: 'cap', label: t('video_download.quality_cap') },
  { value: 'ask', label: t('video_download.quality_ask') },
])
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-cloud-download me-2"></i>{{ $t('video.download.title') }}</h6>
    <p class="form-hint">{{ $t('video.download.description') }}</p>

    <div class="form-group">
      <label>{{ $t('video.download.url') }}</label>
      <input
        v-model="urlText"
        type="text"
        class="form-input"
        placeholder="https://..."
        @change="commitUrl"
      />
    </div>

    <SettingsCollapsible storage-key="video_download_advanced">
      <div class="form-group">
        <label>{{ $t('video_download.quality_mode') }}</label>
        <AppSelect
          :model-value="String(formatIntent.mode ?? 'auto')"
          :options="modeOptions"
          @update:model-value="onModeChange"
        />
      </div>

      <div v-if="formatIntent.mode === 'cap'" class="form-group">
        <label>{{ $t('video_download.max_height') }}</label>
        <input
          v-model.number="maxHeightLocal"
          type="number"
          class="form-input"
          min="1"
          step="1"
          placeholder="1080"
          @change="commitMaxHeight"
        />
      </div>

      <div class="form-group">
        <label>{{ $t('video.download.filename') }}</label>
        <input
          v-model="titleText"
          type="text"
          class="form-input"
          @change="commitTitle"
        />
      </div>
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
