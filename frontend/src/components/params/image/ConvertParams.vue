<script setup lang="ts">
/**
 * image.convert 參數元件（統一參數元件 spec §5；批 4 Task 4.1）。
 * 契約：params/context/fileInfo in、update:params out——host 統一收發，本元件不呼叫 API。
 * UI 沿舊 components/image/panels/ImageConvertPanel.vue 視覺與控件；核心 pattern 同
 * CutParams.vue（one-shot lastEmitted＋commit 即正規化＋shallowEqual 淺層註記），因為
 * resizeMode/scale% 兩個本地鏡射 ref 有「使用者輸入中被外部寫入打斷」的風險（沿
 * TranscodeParams.vue 的 resolution custom 響應式衍生 pattern）。
 *
 * resizeMode（'original'|'scale'|'custom'）＝UI 衍生，非後端欄位：
 *   - params.scale 有值（number）→ 'scale'
 *   - params.width 或 params.height 有值 → 'custom'
 *   - 皆無 → 'original'
 * scale UI 以 % 顯示（10–200），params 存比值（0.1–2.0，÷100/×100 衍生，沿 CutParams.vue
 * 秒數↔HH:MM:SS 顯示轉換 pattern）。mode 切換時互斥 commit（scale 模式清 width/height，
 * custom 模式清 scale）——buildSubmit 對這組互斥另有最後一道防線清理（見 convert.meta.ts）。
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import { META as CONVERT_META } from './convert.meta'

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
}>()
const emit = defineEmits<{ 'update:params': [Record<string, unknown>] }>()

const { t } = useI18n()

/** 鍵集合＋逐鍵 Object.is；用來判斷 watch 收到的 params 是否＝上次自己 emit 的值（回流） */
function shallowEqual(a: Record<string, unknown>, b: Record<string, unknown>): boolean {
  const ak = Object.keys(a)
  const bk = Object.keys(b)
  if (ak.length !== bk.length) return false
  return ak.every((k) => Object.is(a[k], b[k]))
}

function fieldVisible(name: string): boolean {
  const f = CONVERT_META.schema.find((x) => x.name === name)
  return f?.visibleWhen ? f.visibleWhen(props.params) : true
}

const outputFormat = computed(() => String(props.params.output_format ?? 'png'))
const qualityVisible = computed(() => fieldVisible('quality'))
const coalesceVisible = computed(() => fieldVisible('coalesce'))

type ResizeMode = 'original' | 'scale' | 'custom'
function deriveResizeMode(p: Record<string, unknown>): ResizeMode {
  if (typeof p.scale === 'number' && Number.isFinite(p.scale)) return 'scale'
  if (typeof p.width === 'number' || typeof p.height === 'number') return 'custom'
  return 'original'
}

const resizeMode = ref<ResizeMode>(deriveResizeMode(props.params))
const scalePercent = ref(
  typeof props.params.scale === 'number' ? Math.round(props.params.scale * 100) : 100,
)
const widthLocal = ref<number | null>(typeof props.params.width === 'number' ? props.params.width : null)
const heightLocal = ref<number | null>(typeof props.params.height === 'number' ? props.params.height : null)

let lastEmitted: Record<string, unknown> | null = null

watch(
  () => props.params,
  (p) => {
    // one-shot：watch 一觸發就消費 lastEmitted，無論此次是回流還是外部寫入，永不 stale
    const echo = lastEmitted
    lastEmitted = null
    if (echo && shallowEqual(p, echo)) return
    resizeMode.value = deriveResizeMode(p)
    if (typeof p.scale === 'number' && Number.isFinite(p.scale)) {
      scalePercent.value = Math.round(p.scale * 100)
    }
    widthLocal.value = typeof p.width === 'number' ? p.width : null
    heightLocal.value = typeof p.height === 'number' ? p.height : null
  },
  { deep: true },
)

function commit(next: Record<string, unknown>) {
  lastEmitted = next
  emit('update:params', next)
}
function commitPatch(patch: Record<string, unknown>) {
  commit({ ...props.params, ...patch })
}

function onFormatChange(v: string) {
  commitPatch({ output_format: v })
}

function onResizeModeChange(mode: ResizeMode) {
  resizeMode.value = mode
  if (mode === 'scale') {
    commitPatch({ scale: scalePercent.value / 100, width: undefined, height: undefined })
  } else if (mode === 'custom') {
    commitPatch({ width: widthLocal.value ?? undefined, height: heightLocal.value ?? undefined, scale: undefined })
  } else {
    commitPatch({ scale: undefined, width: undefined, height: undefined })
  }
}

function onScaleChange(v: number) {
  scalePercent.value = v
  commitPatch({ scale: v / 100 })
}
function onWidthChange() {
  commitPatch({ width: widthLocal.value ?? undefined })
}
function onHeightChange() {
  commitPatch({ height: heightLocal.value ?? undefined })
}
function onQualityChange(v: number) {
  commitPatch({ quality: v })
}
function onCoalesceChange(v: boolean) {
  commitPatch({ coalesce: v })
}

const convertFormats = [
  { value: 'png', label: 'PNG' },
  { value: 'jpg', label: 'JPEG' },
  { value: 'webp', label: 'WebP' },
  { value: 'gif', label: 'GIF' },
  { value: 'bmp', label: 'BMP' },
]

const resizeModeOptions = computed(() => [
  { value: 'original', label: t('image.convert.original_size') },
  { value: 'scale', label: t('image.convert.scale') },
  { value: 'custom', label: t('image.convert.custom_size') },
])

const scaledSizeHint = computed(() => {
  const fw = props.fileInfo?.width
  const fh = props.fileInfo?.height
  if (typeof fw !== 'number' || typeof fh !== 'number') return ''
  const w = Math.round((fw * scalePercent.value) / 100)
  const h = Math.round((fh * scalePercent.value) / 100)
  return `${fw} × ${fh} → ${w} × ${h}`
})
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-arrow-repeat me-2"></i>{{ $t('image.convert.title') }}</h6>
    <p class="form-hint">{{ $t('image.convert.description') }}</p>

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect :model-value="outputFormat" :options="convertFormats" @update:model-value="onFormatChange" />
    </div>

    <div class="form-group">
      <label>{{ $t('image.convert.resize_mode') }}</label>
      <AppSelect
        :model-value="resizeMode"
        :options="resizeModeOptions"
        @update:model-value="(v) => onResizeModeChange(v as ResizeMode)"
      />
    </div>

    <div v-if="resizeMode === 'scale'" class="form-group">
      <label>{{ $t('image.convert.scale_label') }} {{ scalePercent }}%</label>
      <AppRange
        :model-value="scalePercent"
        :min="10"
        :max="200"
        @update:model-value="onScaleChange"
      />
      <small class="form-hint">{{ scaledSizeHint }}</small>
    </div>

    <div v-if="resizeMode === 'custom'" class="form-group size-inputs">
      <div class="size-input-group">
        <label>{{ $t('common.width') }}</label>
        <input
          v-model.number="widthLocal"
          type="number" class="form-input" placeholder="px" min="1"
          @change="onWidthChange"
        />
      </div>
      <span class="size-separator">×</span>
      <div class="size-input-group">
        <label>{{ $t('common.height') }}</label>
        <input
          v-model.number="heightLocal"
          type="number" class="form-input" placeholder="px" min="1"
          @change="onHeightChange"
        />
      </div>
    </div>
    <small v-if="resizeMode === 'custom'" class="form-hint">{{ $t('image.convert.aspect_ratio_hint') }}</small>

    <SettingsCollapsible v-if="qualityVisible" storage-key="image_convert_advanced">
      <div class="form-group">
        <label>{{ $t('image.convert.quality') }} {{ Number(params.quality ?? 85) }}%</label>
        <AppRange
          :model-value="Number(params.quality ?? 85)"
          :min="1"
          :max="100"
          @update:model-value="onQualityChange"
        />
        <small class="form-hint">{{ $t('image.convert.quality_hint') }}</small>
      </div>
    </SettingsCollapsible>

    <div v-if="coalesceVisible" class="form-group">
      <AppToggle :model-value="Boolean(params.coalesce)" @update:model-value="onCoalesceChange">
        {{ $t('image.convert.coalesce') }}
      </AppToggle>
      <small class="form-hint">{{ $t('image.convert.coalesce_hint') }}</small>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
