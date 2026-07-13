<script setup lang="ts">
/**
 * image.filter 參數元件（統一參數元件 spec §5；批 4 Task 4.2 ⭐合併 task）。
 * 契約：params/context/fileInfo in、update:params out——host 統一收發，本元件不呼叫 API。
 * 合併自舊 components/image/panels/ImageAdjustPanel.vue（brightness/contrast/saturation/
 * hue/sharpness/warmth）＋ImageFilterPanel.vue（grayscale/sepia/invert/blur/vignette）——
 * 兩者打同一後端 /image/filter，UI 視覺沿舊兩 panel 逐欄照搬（見 filter.meta.ts 檔頭）。
 *
 * ⭐ fieldGroup 分組渲染（batch4-recon.md §3／Surprise 3）：本元件經 `fieldGroup?:
 * 'adjust'|'filter'` prop（非 ToolParamHost 宣告的正式 prop，經單根元件 attrs fallthrough
 * 透傳——沿 CropParams.vue 的 canvasCropRect 先例）決定只渲染哪一組欄位：
 *   - fieldGroup='adjust' → 只顯示 6 個 adjust 欄位＋adjust 專屬 reset
 *   - fieldGroup='filter' → 只顯示 5 個 filter 欄位＋filter 專屬 reset
 *   - 未傳（pipeline 語境）→ 兩組都顯示（各自標題＋各自 reset），欄位全集
 * showAdjust/showFilter 兩個 computed 是唯一的分組真相來源，reset／preview 組裝都靠它們
 * 泛化涵蓋「未傳＝全集」情況，不需要為 undefined 另寫分支。
 *
 * UI↔後端尺度轉換（逐欄核對舊 panel getParams()，非統一比例）：
 *   brightness/contrast/saturation/sharpness：UI 0-300(%) ↔ 後端 0-3.0（/100）
 *   hue：UI -180~180(度) ↔ 後端原值直傳（無轉換，舊 ImageAdjustPanel.getParams() hue 直傳）
 *   warmth：UI -100~100 ↔ 後端 -1.0~1.0（/100）
 *   grayscale/sepia/invert/vignette：UI 0-100(%) ↔ 後端 0-1.0（/100）
 *   blur：UI px 直傳 ↔ 後端 px 直傳（無轉換，舊 ImageFilterPanel.getParams() blur 直傳）；
 *   UI 滑桿沿舊 panel 侷限 max=20（AppRange :max，非 schema 限制——後端/schema 上限較寬 100）
 *
 * 本元件不維護鏡射 props.params 的本地 ref（所有欄位皆直接讀 props.params 的 computed），
 * 故不需要 CutParams/CropParams 那套 one-shot lastEmitted 回流判別——沿 CompressParams.vue
 * 同款理由（無「本地編輯中途被外部寫入打斷」的風險，見該檔檔頭註解 :77-80）。
 *
 * preview-change emit（WebGL 即時預覽，語意＝舊兩 panel :43／:33-54）：watch(params,fieldGroup)
 * → emit 11 欄 FilterPreview，自己組讀 props.params 實際值、非自己組讀中性值。fieldGroup 未傳
 * （showAdjust/showFilter 皆 true）時兩組皆讀實際值，天然等於「全集直傳」，不需特判。
 * host 未宣告 preview-change emit，經 attrs fallthrough 透傳給 ImageView（同 canvasCropRect
 * 透傳機制；VideoView.vue 的 video.crop 掛載點已驗證 @update:show-crop-overlay 走這條路）。
 */
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppRange from '@/components/common/AppRange.vue'
import type { FilterPreview } from '@/components/image/panels/filterTypes'

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
  fieldGroup?: 'adjust' | 'filter'
}>()
const emit = defineEmits<{
  'update:params': [Record<string, unknown>]
  'preview-change': [FilterPreview]
}>()

const { t } = useI18n()

function commitPatch(patch: Record<string, unknown>) {
  emit('update:params', { ...props.params, ...patch })
}

// ─── 分組真相來源：undefined fieldGroup（pipeline 全集）＝兩組皆顯示 ──────────────
const showAdjust = computed(() => props.fieldGroup !== 'filter')
const showFilter = computed(() => props.fieldGroup !== 'adjust')

// ─── adjust 6 欄：UI 百分比/度數 ↔ 後端 0-3.0/原值 ──────────────────────────────
const brightness = computed(() => Math.round(Number(props.params.brightness ?? 1) * 100))
const contrast = computed(() => Math.round(Number(props.params.contrast ?? 1) * 100))
const saturation = computed(() => Math.round(Number(props.params.saturation ?? 1) * 100))
const hue = computed(() => Number(props.params.hue ?? 0))
const sharpness = computed(() => Math.round(Number(props.params.sharpness ?? 1) * 100))
const warmth = computed(() => Math.round(Number(props.params.warmth ?? 0) * 100))

function onBrightnessChange(v: number) { commitPatch({ brightness: v / 100 }) }
function onContrastChange(v: number) { commitPatch({ contrast: v / 100 }) }
function onSaturationChange(v: number) { commitPatch({ saturation: v / 100 }) }
function onHueChange(v: number) { commitPatch({ hue: v }) }
function onSharpnessChange(v: number) { commitPatch({ sharpness: v / 100 }) }
function onWarmthChange(v: number) { commitPatch({ warmth: v / 100 }) }

function resetAdjust() {
  commitPatch({ brightness: 1, contrast: 1, saturation: 1, hue: 0, sharpness: 1, warmth: 0 })
}

// ─── filter 5 欄：UI 百分比/px ↔ 後端 0-1.0/px 直傳 ─────────────────────────────
const grayscale = computed(() => Math.round(Number(props.params.grayscale ?? 0) * 100))
const sepia = computed(() => Math.round(Number(props.params.sepia ?? 0) * 100))
const invert = computed(() => Math.round(Number(props.params.invert ?? 0) * 100))
const blur = computed(() => Number(props.params.blur ?? 0))
const vignette = computed(() => Math.round(Number(props.params.vignette ?? 0) * 100))

function onGrayscaleChange(v: number) { commitPatch({ grayscale: v / 100 }) }
function onSepiaChange(v: number) { commitPatch({ sepia: v / 100 }) }
function onInvertChange(v: number) { commitPatch({ invert: v / 100 }) }
function onBlurChange(v: number) { commitPatch({ blur: v }) }
function onVignetteChange(v: number) { commitPatch({ vignette: v / 100 }) }

function resetFilter() {
  commitPatch({ grayscale: 0, sepia: 0, invert: 0, blur: 0, vignette: 0 })
}

// ─── preview-change：自己組讀實際值、非自己組讀中性值（見檔頭說明） ──────────────
const preview = computed<FilterPreview>(() => ({
  brightness: showAdjust.value ? Number(props.params.brightness ?? 1) : 1,
  contrast: showAdjust.value ? Number(props.params.contrast ?? 1) : 1,
  saturation: showAdjust.value ? Number(props.params.saturation ?? 1) : 1,
  hue: showAdjust.value ? Number(props.params.hue ?? 0) : 0,
  sharpness: showAdjust.value ? Number(props.params.sharpness ?? 1) : 1,
  warmth: showAdjust.value ? Number(props.params.warmth ?? 0) : 0,
  grayscale: showFilter.value ? Number(props.params.grayscale ?? 0) : 0,
  sepia: showFilter.value ? Number(props.params.sepia ?? 0) : 0,
  invert: showFilter.value ? Number(props.params.invert ?? 0) : 0,
  blur: showFilter.value ? Number(props.params.blur ?? 0) : 0,
  vignette: showFilter.value ? Number(props.params.vignette ?? 0) : 0,
}))

watch(preview, (val) => emit('preview-change', val), { immediate: true })
</script>

<template>
  <div class="function-settings">
    <template v-if="showAdjust">
      <h6 class="settings-title"><i class="bi bi-sliders me-2"></i>{{ $t('image.adjust.title') }}</h6>
      <p class="form-hint">{{ $t('image.adjust.description') }}</p>

      <div class="form-group">
        <label>{{ $t('image.adjust.brightness') }} <span class="param-value">{{ brightness }}%</span></label>
        <AppRange :model-value="brightness" :min="0" :max="300" :step="1" @update:model-value="onBrightnessChange" />
      </div>

      <div class="form-group">
        <label>{{ $t('image.adjust.contrast') }} <span class="param-value">{{ contrast }}%</span></label>
        <AppRange :model-value="contrast" :min="0" :max="300" :step="1" @update:model-value="onContrastChange" />
      </div>

      <div class="form-group">
        <label>{{ $t('image.adjust.saturation') }} <span class="param-value">{{ saturation }}%</span></label>
        <AppRange :model-value="saturation" :min="0" :max="300" :step="1" @update:model-value="onSaturationChange" />
      </div>

      <div class="form-group">
        <label>{{ $t('image.adjust.sharpness') }} <span class="param-value">{{ sharpness }}%</span></label>
        <AppRange :model-value="sharpness" :min="0" :max="300" :step="1" @update:model-value="onSharpnessChange" />
      </div>

      <div class="form-group">
        <label>{{ $t('image.adjust.hue') }} <span class="param-value">{{ hue > 0 ? '+' : '' }}{{ hue }}°</span></label>
        <AppRange :model-value="hue" :min="-180" :max="180" :step="1" @update:model-value="onHueChange" />
      </div>

      <div class="form-group">
        <label>
          {{ $t('image.adjust.warmth') }}
          <span class="param-value">
            {{ warmth > 0 ? `${$t('image.adjust.warm')} +${warmth}` : warmth < 0 ? `${$t('image.adjust.cool')} ${warmth}` : '0' }}
          </span>
        </label>
        <AppRange :model-value="warmth" :min="-100" :max="100" :step="1" @update:model-value="onWarmthChange" />
      </div>

      <div class="form-group">
        <button class="btn-secondary" @click="resetAdjust">
          <i class="bi bi-arrow-counterclockwise"></i>{{ $t('image.adjust.reset') }}
        </button>
      </div>
    </template>

    <template v-if="showFilter">
      <h6 class="settings-title"><i class="bi bi-palette-fill me-2"></i>{{ $t('image.filter.title') }}</h6>
      <p class="form-hint">{{ $t('image.filter.description') }}</p>

      <div class="form-group">
        <label>{{ $t('image.filter.grayscale') }} <span class="param-value">{{ grayscale }}%</span></label>
        <AppRange :model-value="grayscale" :min="0" :max="100" :step="1" @update:model-value="onGrayscaleChange" />
      </div>

      <div class="form-group">
        <label>{{ $t('image.filter.sepia') }} <span class="param-value">{{ sepia }}%</span></label>
        <AppRange :model-value="sepia" :min="0" :max="100" :step="1" @update:model-value="onSepiaChange" />
      </div>

      <div class="form-group">
        <label>{{ $t('image.filter.invert') }} <span class="param-value">{{ invert }}%</span></label>
        <AppRange :model-value="invert" :min="0" :max="100" :step="1" @update:model-value="onInvertChange" />
      </div>

      <div class="form-group">
        <label>{{ $t('image.filter.blur') }} <span class="param-value">{{ blur }}px</span></label>
        <AppRange :model-value="blur" :min="0" :max="20" :step="1" @update:model-value="onBlurChange" />
      </div>

      <div class="form-group">
        <label>{{ $t('image.filter.vignette') }} <span class="param-value">{{ vignette }}%</span></label>
        <AppRange :model-value="vignette" :min="0" :max="100" :step="1" @update:model-value="onVignetteChange" />
      </div>

      <div class="form-group">
        <button class="btn-secondary" @click="resetFilter">
          <i class="bi bi-arrow-counterclockwise"></i>{{ $t('image.filter.reset') }}
        </button>
      </div>
    </template>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
