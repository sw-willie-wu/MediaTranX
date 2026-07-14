<script setup lang="ts">
/**
 * document.pdf_convert 參數元件（統一參數元件 spec §5；批 4 Task 4.5 Part B）。
 * UI 沿舊 components/document/panels/DocumentPdfConvertPanel.vue：單一 output_format
 * AppSelect，選項依副檔名動態過濾（images 僅 PDF）。
 * 契約：params/context/fileInfo in、update:params out——host 統一收發，本元件不呼叫 API。
 *
 * ⚠ currentFileExt 選配 prop 透過 fallthrough attrs 傳入（沿 OcrParams.vue persistKey/
 * i18nPrefix 先例——ToolParamHost 未宣告的 prop 會自動落到 $attrs、轉發到本元件）：
 * DocumentView.vue 的掛載點傳 `:current-file-ext="currentFileExt"`。
 *
 * ⚠ ext 未知時的兩種語意不可混淆（2026-07-13 Task 4.5 review fix）：
 * - **未傳**（pipeline context 掛載，PipelineParamForm 不轉發 fallthrough current-file-ext）
 *   → 副檔名「不知道」，不是「確定非 PDF」。與 legacy 表單 parity：選單顯示全部三個選項
 *   （txt/md/images），且防 stale watch **不修正**——pipeline 節點的 output_format='images'
 *   是合法值（例如上游會產生 PDF），光渲染編輯器不該靜默改寫 recipe。
 * - **明確傳了非 'pdf' 的值**（tool 頁掛載，DocumentView 知道目前檔案副檔名）→ 確定非
 *   PDF，images 選項隱藏；且若殘留 output_format==='images' 視為 stale，防 stale watch
 *   修正回 'txt'。
 * isKnownNonPdf = currentFileExt 有值 && !== 'pdf'；只有這個條件成立才隱藏 images／觸發
 * 修正，ext undefined 或 ='pdf' 都不算「已知非 PDF」。
 *
 * 單一 enum 欄位、無多欄位互斥，直接用 computed get/set 綁 AppSelect（沿
 * RemoveBgParams.vue 慣例）；額外一個 watch 處理「已知非 PDF 時殘留 output_format='images'」
 * 防 stale（見 batch4-recon.md §9 pdf_convert 節＋brief Part B）——涵蓋掛載時就是 stale、
 * 以及掛載後切檔從 PDF 換成已知非 PDF 兩種情形。
 */
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
  currentFileExt?: string
}>()
const emit = defineEmits<{ 'update:params': [Record<string, unknown>] }>()

const { t } = useI18n()

// 已知非 PDF：ext 有值且不是 'pdf'。ext undefined（pipeline 常見）不算「已知非 PDF」——
// 副檔名未知時不能假設非 PDF，見檔頭說明。
const isKnownNonPdf = computed(() => !!props.currentFileExt && props.currentFileExt !== 'pdf')

const outputFormatOptions = computed(() => {
  const opts = [
    { value: 'txt', label: t('document.pdf_convert.text_format') },
    { value: 'md', label: t('document.pdf_convert.markdown_format') },
  ]
  if (!isKnownNonPdf.value) opts.push({ value: 'images', label: t('document.pdf_convert.images_format') })
  return opts
})

const outputFormat = computed<string>({
  get: () => (typeof props.params.output_format === 'string' ? props.params.output_format : 'txt'),
  set: (v) => emit('update:params', { ...props.params, output_format: v }),
})

// 已知非 PDF 時若殘留 output_format==='images'（切檔、或舊 recipe/agent 塞入的值）→ 修正回
// 'txt'，防止送出時後端 ValueError（422）。immediate 涵蓋掛載當下即 stale 的情形。
// ext 未知（isKnownNonPdf=false，pipeline 常見）永不觸發修正——不可在副檔名未知時
// 靜默改寫 recipe 裡合法的 'images' 值。
watch(
  () => [isKnownNonPdf.value, props.params.output_format] as const,
  ([knownNonPdf, fmt]) => {
    if (knownNonPdf && fmt === 'images') {
      emit('update:params', { ...props.params, output_format: 'txt' })
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-file-earmark-pdf-fill me-2"></i>{{ $t('document.pdf_convert.title') }}</h6>
    <p class="form-hint">{{ $t('document.pdf_convert.description') }}</p>

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect v-model="outputFormat" :options="outputFormatOptions" />
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
