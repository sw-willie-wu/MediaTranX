<script setup lang="ts">
/**
 * image.compress 參數元件（統一參數元件 spec §5；批 4 Task 4.1）。
 * 契約：params/context/fileInfo in、update:params out——host 統一收發，本元件不呼叫 API。
 * UI 沿舊 components/image/panels/ImageCompressPanel.vue 視覺與控件。多數欄位直接讀
 * props.params 的 computed（無本地鏡射 ref），故不需要 CutParams.vue 那套 one-shot
 * lastEmitted 回流判別；唯一的本地狀態是 gif_colors 換圖判斷（見下方）。
 *
 * resultMeta：舊 panel 有 :result-meta prop（顯示 saved_ratio 摘要），本元件契約沒有這個
 * prop（host 未宣告，見 ToolParamHost.vue 未宣告 result-meta）——沿 CropParams.vue 的
 * canvasCropRect 透傳先例：ImageView 直接在 <ToolParamHost :result-meta="..."> 上掛這個
 * attr，經單根元件 attrs fallthrough 穿透到本元件（本元件自己宣告 resultMeta prop 接住）。
 *
 * ⭐ palette 動態上限 + 換圖重置 + userTouched 追蹤（批 4 地面實況 §1／Surprise 7，鏡射舊
 * panel :21 邏輯，收進元件）：
 * 舊 panel 用 props.fileId 當「圖片身分」判斷是否為「換了一張新圖」（換圖才重置 gif_colors
 * 為新調色盤預設值；同一張圖的 post-task reload／背景 palette patch 不可清掉使用者已調的值）。
 * 本元件的 props 契約沒有 fileId（ToolParamHost 的 <component> 模板只傳 params/context/
 * file-info，fileId 是 host 自己宣告的 prop、不會 fallthrough——它與 file-info 屬性名不同，
 * 不能沿用 canvasCropRect 的透傳手法而不加一個新 attr）。改用 fileInfo 本身的「非 palette
 * 欄位」（width/height/format/mode）組字串當身分替代 key：
 *   - 換圖：width/height/format/mode 任一變 → 視為新圖，重置 userTouched、依新 palette_size
 *     （或 GIF 預設 256）重算 gif_colors。
 *   - 背景 palette patch（useDomainInfoCache.patch 只新增 palette_size，不動其餘欄位）／
 *     post-task reload（compress 不改變尺寸格式）→ key 不變 → 不重置，僅 gifColorsMax
 *     的 computed 自然反映新 palette_size，多一道 watch 夾限（超過新上限才降下來)。
 * 已知限制（非 fileId 判準的代價，report 記為 concern）：兩張「尺寸/格式/mode 完全相同」
 * 的不同 GIF 前後切換，本元件會誤判為「同一張圖」而不重置——這是用 fileInfo 形狀替代
 * fileId 身分判準的固有邊界情況，機率低（同尺寸同 mode 的不同 GIF）。
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppRange from '@/components/common/AppRange.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
  resultMeta?: Record<string, unknown> | null
}>()
const emit = defineEmits<{ 'update:params': [Record<string, unknown>] }>()

const { t } = useI18n()

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(Math.max(v, lo), hi)
}

// ─── 格式判斷（依 fileInfo.format，沿舊 panel isGif/isPng/isJpeg/isWebp） ───────────
const formatUpper = computed(() => String(props.fileInfo?.format ?? '').toUpperCase())
const isGif = computed(() => formatUpper.value === 'GIF')
const isPng = computed(() => formatUpper.value === 'PNG')
const isJpeg = computed(() => formatUpper.value === 'JPEG' || formatUpper.value === 'JPG')
const isWebp = computed(() => formatUpper.value === 'WEBP')

// ─── gif_colors：palette 動態上限 ───────────────────────────────────────────
const gifColorsMax = computed(() => {
  const palette = props.fileInfo?.palette_size
  return clamp(typeof palette === 'number' ? palette : 256, 2, 256)
})

function gifColorsDefault(info: Record<string, unknown> | null | undefined): number {
  if (String(info?.format ?? '').toUpperCase() !== 'GIF') return 256
  const palette = info?.palette_size
  return clamp(typeof palette === 'number' ? palette : 256, 2, 256)
}

/** fileInfo 身分替代 key（見檔頭註解）：不含 palette_size，palette 背景 patch 不改變它 */
function infoKey(info: Record<string, unknown> | null | undefined): string | null {
  if (!info) return null
  return `${info.width}x${info.height}:${info.format}:${info.mode}`
}

// 本元件不維護任何鏡射 props.params 的本地 ref（strength/gif_frame_drop/png_lossy 等皆直接
// 讀 props.params 的 computed），故不需要 CutParams/CropParams 那套 one-shot lastEmitted
// 回流判別——沒有「本地編輯中途被外部寫入打斷」的風險。唯一的本地狀態是 gif_colors 的換圖
// 判斷（lastInfoKey/userTouchedColors，見下方），其輸入是 fileInfo 不是 params，不受此影響。
function commitPatch(patch: Record<string, unknown>) {
  emit('update:params', { ...props.params, ...patch })
}

const lastInfoKey = ref<string | null>(null)
const userTouchedColors = ref(false)

// immediate：掛載當下就依現有 fileInfo 判斷是否要 seed gif_colors（見檔頭 key 設計說明）。
watch(
  () => props.fileInfo,
  (info) => {
    const key = infoKey(info)
    if (key === lastInfoKey.value) return // 同一張圖（含 palette 背景 patch／post-task reload）
    lastInfoKey.value = key
    userTouchedColors.value = false
    if (String(info?.format ?? '').toUpperCase() === 'GIF') {
      commitPatch({ gif_colors: gifColorsDefault(info) })
    }
  },
  { immediate: true },
)

// palette 上限縮小（例如稍後才拿到真實 palette_size）→ 現值超過上限才夾回
watch(gifColorsMax, (newMax) => {
  const current = props.params.gif_colors
  if (typeof current === 'number' && current > newMax) {
    commitPatch({ gif_colors: newMax })
  }
})

function onGifColorsUpdate(v: number) {
  userTouchedColors.value = true
  commitPatch({ gif_colors: v })
}

// ─── 其他欄位：一般 boolean/number toggle（無外部寫回位移需求，直接讀 props.params 顯示） ──
const strength = computed(() => Number(props.params.strength ?? 75))
const gifColorsDisplay = computed(() =>
  typeof props.params.gif_colors === 'number' ? props.params.gif_colors : gifColorsDefault(props.fileInfo),
)
const gifFrameDrop = computed(() => Number(props.params.gif_frame_drop ?? 0))
const gifOptimizeTransparency = computed(() => Boolean(props.params.gif_optimize_transparency ?? true))
const pngMode = computed<'lossy' | 'lossless'>(() => (props.params.png_lossy === false ? 'lossless' : 'lossy'))
const jpegProgressive = computed(() => Boolean(props.params.jpeg_progressive ?? true))
const jpegKeepMetadata = computed(() => Boolean(props.params.jpeg_keep_metadata ?? false))
const webpLossless = computed(() => Boolean(props.params.webp_lossless ?? false))

function onStrengthChange(v: number) {
  commitPatch({ strength: v })
}
function onGifFrameDropChange(v: string | number) {
  commitPatch({ gif_frame_drop: Number(v) })
}
function onGifOptimizeTransparencyChange(v: boolean) {
  commitPatch({ gif_optimize_transparency: v })
}
function onPngModeChange(v: string) {
  commitPatch({ png_lossy: v === 'lossy' })
}
function onJpegProgressiveChange(v: boolean) {
  commitPatch({ jpeg_progressive: v })
}
function onJpegKeepMetadataChange(v: boolean) {
  commitPatch({ jpeg_keep_metadata: v })
}
function onWebpLosslessChange(v: boolean) {
  commitPatch({ webp_lossless: v })
}

// ─── resultSummary（fallthrough resultMeta，沿舊 panel :92-109） ───────────────────
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const resultSummary = computed(() => {
  const meta = props.resultMeta
  if (!meta) return null
  const ratio = meta.saved_ratio
  if (typeof ratio !== 'number') return null
  const orig = typeof meta.original_size === 'number' ? meta.original_size : null
  const out = typeof meta.output_size === 'number' ? meta.output_size : null
  const sizeInfo = orig !== null && out !== null ? `${formatBytes(orig)} → ${formatBytes(out)}` : null
  if (ratio > 0) return { kind: 'saved' as const, pct: Math.round(ratio * 100), sizeInfo }
  if (ratio < 0) return { kind: 'larger' as const, pct: Math.round(-ratio * 100), sizeInfo }
  return { kind: 'no_change' as const, pct: 0, sizeInfo }
})

const gifFrameDropOptions = computed(() => [
  { value: 0, label: t('image.compress.gif_frame_drop_none') },
  { value: 2, label: t('image.compress.gif_frame_drop_2') },
  { value: 3, label: t('image.compress.gif_frame_drop_3') },
  { value: 4, label: t('image.compress.gif_frame_drop_4') },
])

const pngModeOptions = computed(() => [
  { value: 'lossy', label: t('image.compress.png_mode_lossy') },
  { value: 'lossless', label: t('image.compress.png_mode_lossless') },
])
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-file-zip-fill me-2"></i>{{ $t('image.compress.title') }}</h6>
    <p class="form-hint">{{ $t('image.compress.description') }}</p>

    <div
      v-if="resultSummary"
      class="compress-result-summary"
      :class="resultSummary.kind === 'saved' ? 'compress-result-saved' : 'compress-result-neutral'"
    >
      <template v-if="resultSummary.kind === 'saved'">
        <i class="bi bi-check-circle-fill me-1"></i>
        {{ $t('image.compress.saved', { pct: resultSummary.pct }) }}
      </template>
      <template v-else-if="resultSummary.kind === 'larger'">
        <i class="bi bi-exclamation-triangle me-1"></i>
        {{ $t('image.compress.larger', { pct: resultSummary.pct }) }}
      </template>
      <template v-else>
        <i class="bi bi-dash-circle me-1"></i>
        {{ $t('image.compress.no_change') }}
      </template>
      <span v-if="resultSummary.sizeInfo" class="compress-result-sizes">{{ resultSummary.sizeInfo }}</span>
    </div>

    <div class="form-group">
      <label>{{ $t('image.compress.strength') }} {{ strength }}%</label>
      <AppRange :model-value="strength" :min="1" :max="100" @update:model-value="onStrengthChange" />
      <small class="form-hint">{{ $t('image.compress.strength_hint') }}</small>
    </div>

    <SettingsCollapsible v-if="isPng" storage-key="image_compress_png_advanced">
      <div class="form-group">
        <label>{{ $t('image.compress.png_mode') }}</label>
        <AppSelect :model-value="pngMode" :options="pngModeOptions" @update:model-value="onPngModeChange" />
      </div>
    </SettingsCollapsible>

    <SettingsCollapsible v-if="isJpeg" storage-key="image_compress_jpeg_advanced">
      <div class="form-group">
        <AppToggle :model-value="jpegProgressive" @update:model-value="onJpegProgressiveChange">
          {{ $t('image.compress.jpeg_progressive') }}
        </AppToggle>
      </div>
      <div class="form-group">
        <AppToggle :model-value="jpegKeepMetadata" @update:model-value="onJpegKeepMetadataChange">
          {{ $t('image.compress.jpeg_keep_metadata') }}
        </AppToggle>
      </div>
    </SettingsCollapsible>

    <SettingsCollapsible v-if="isWebp" storage-key="image_compress_webp_advanced">
      <div class="form-group">
        <AppToggle :model-value="webpLossless" @update:model-value="onWebpLosslessChange">
          {{ $t('image.compress.webp_lossless') }}
        </AppToggle>
      </div>
    </SettingsCollapsible>

    <div v-if="isGif && typeof fileInfo?.palette_size === 'number'" class="form-hint gif-source-colors-hint">
      {{ $t('image.compress.gif_source_colors', { n: fileInfo.palette_size }) }}
    </div>

    <SettingsCollapsible v-if="isGif" storage-key="image_compress_advanced">
      <div class="form-group">
        <label>{{ $t('image.compress.gif_colors') }} {{ gifColorsDisplay }}</label>
        <AppRange
          :model-value="gifColorsDisplay"
          :min="2"
          :max="gifColorsMax"
          @update:model-value="onGifColorsUpdate"
        />
        <small class="form-hint">{{ $t('image.compress.gif_colors_hint') }}</small>
      </div>

      <div class="form-group">
        <label>{{ $t('image.compress.gif_frame_drop') }}</label>
        <AppSelect :model-value="gifFrameDrop" :options="gifFrameDropOptions" @update:model-value="onGifFrameDropChange" />
      </div>

      <div class="form-group">
        <AppToggle :model-value="gifOptimizeTransparency" @update:model-value="onGifOptimizeTransparencyChange">
          {{ $t('image.compress.gif_optimize_transparency') }}
        </AppToggle>
      </div>
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';

.compress-result-summary {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.8rem;
  margin-bottom: 0.75rem;

  &.compress-result-saved {
    color: var(--text-success, #4caf50);
  }

  &.compress-result-neutral {
    color: var(--text-muted);
  }

  .compress-result-sizes {
    color: var(--text-muted);
    margin-left: 0.25rem;
  }
}
</style>
