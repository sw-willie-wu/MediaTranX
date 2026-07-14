<script setup lang="ts">
/**
 * video.crop 參數元件（統一參數元件 spec §5；批 2 Task 2.1）。
 * 契約：params/context/fileInfo in、update:params out——host 統一收發，本元件不呼叫 API。
 * 沿 CutParams.vue 核心 pattern：顯示值＝響應式衍生＋本地編輯不打斷——
 * watch(props.params) 時對「上次自己 emit 的值」做 value-diff（one-shot lastEmitted）：
 *   相同（自身 emit 回流）→ 不重推顯示值（使用者輸入中不被打斷）
 *   不同（外部寫入：agent setField/setParams/seed/canvas 拖曳/開 recipe）→ 重推顯示值
 *
 * aspectRatio/showCropOverlay 是 UI 便利狀態，不入 params（非後端欄位）：本地 ref＋emit
 * update:aspectRatio / update:showCropOverlay（沿舊 VideoCropPanel 契約，讓 VideoView 接線不變形）。
 * canvasCropRect 是 tool context 專屬 prop，經 ToolParamHost 單根元件 attrs fallthrough 透傳
 * （host 未宣告此 prop/事件，Vue 對單根元件預設自動落到 <component :is>）；pipeline context
 * 不傳此 prop，四欄位仍照常渲染輸入框。
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
  canvasCropRect?: { x: number; y: number; w: number; h: number } | null
}>()
const emit = defineEmits<{
  'update:params': [Record<string, unknown>]
  'update:showCropOverlay': [boolean]
  'update:aspectRatio': [string]
}>()

const { t } = useI18n()

/** 假設 params 為淺層 primitive；鍵集合＋逐鍵 Object.is，用來判斷 watch 收到的 params 是否＝上次自己 emit 的值（回流） */
function shallowEqual(a: Record<string, unknown>, b: Record<string, unknown>): boolean {
  const ak = Object.keys(a)
  const bk = Object.keys(b)
  if (ak.length !== bk.length) return false
  return ak.every((k) => Object.is(a[k], b[k]))
}

function numOrDefault(v: unknown, d: number): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : d
}
function numOrNull(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

const localX = ref(numOrDefault(props.params.x, 0))
const localY = ref(numOrDefault(props.params.y, 0))
const localWidth = ref<number | null>(numOrNull(props.params.width))
const localHeight = ref<number | null>(numOrNull(props.params.height))

let lastEmitted: Record<string, unknown> | null = null

watch(
  () => props.params,
  (p) => {
    // one-shot：watch 一觸發就消費 lastEmitted，無論此次是回流還是外部寫入，永不 stale
    const echo = lastEmitted
    lastEmitted = null
    if (echo && shallowEqual(p, echo)) return
    localX.value = numOrDefault(p.x, 0)
    localY.value = numOrDefault(p.y, 0)
    localWidth.value = numOrNull(p.width)
    localHeight.value = numOrNull(p.height)
  },
  { deep: true },
)

function commit(next: Record<string, unknown>) {
  lastEmitted = next
  emit('update:params', next)
}

function commitX() {
  commit({ ...props.params, x: numOrDefault(localX.value, 0) })
}
function commitY() {
  commit({ ...props.params, y: numOrDefault(localY.value, 0) })
}
function commitWidth() {
  commit({ ...props.params, width: numOrNull(localWidth.value) ?? undefined })
}
function commitHeight() {
  commit({ ...props.params, height: numOrNull(localHeight.value) ?? undefined })
}

// ─── showCropOverlay / aspectRatio：UI 便利狀態，不入 params（鏡射舊 panel :23-24/:31） ──
const showCropOverlay = ref(true)
watch(showCropOverlay, (v) => emit('update:showCropOverlay', v), { immediate: true })

const aspectRatio = ref('free')
watch(aspectRatio, (v) => emit('update:aspectRatio', v))

const aspectOptions = computed(() => [
  { value: 'free', label: t('video.crop.free') },
  { value: '1:1', label: t('video.crop.square') },
  { value: '4:3', label: '4:3' },
  { value: '3:4', label: '3:4' },
  { value: '16:9', label: '16:9' },
  { value: '9:16', label: '9:16' },
])

// ─── canvas 拖曳入向：四捨五入寫回 params（四欄位一次 commit，同時同步本地顯示） ─────
watch(
  () => props.canvasCropRect,
  (rect) => {
    if (!rect) return
    const x = Math.round(rect.x)
    const y = Math.round(rect.y)
    const width = Math.round(rect.w)
    const height = Math.round(rect.h)
    localX.value = x
    localY.value = y
    localWidth.value = width
    localHeight.value = height
    commit({ ...props.params, x, y, width, height })
  },
)

// ─── 縱橫比鎖定：非 free 時 height 依「已提交」的 params.width 反推（鏡射舊 panel :51-55） ──
watch(
  () => [aspectRatio.value, props.params.width] as const,
  ([ratio, w]) => {
    if (ratio === 'free' || typeof w !== 'number') return
    const [wRatio, hRatio] = ratio.split(':').map(Number)
    const h = Math.round((w as number) * hRatio / wRatio)
    if (h === props.params.height) return
    localHeight.value = h
    commit({ ...props.params, height: h })
  },
)

const maxW = computed(() => {
  const fw = props.fileInfo?.width
  return typeof fw === 'number' ? fw - localX.value : 9999
})
const maxH = computed(() => {
  const fh = props.fileInfo?.height
  return typeof fh === 'number' ? fh - localY.value : 9999
})
const maxX = computed(() => {
  const fw = props.fileInfo?.width
  return typeof fw === 'number' ? fw - 1 : 9999
})
const maxY = computed(() => {
  const fh = props.fileInfo?.height
  return typeof fh === 'number' ? fh - 1 : 9999
})
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-crop me-2"></i>{{ $t('video.crop.title') }}</h6>
    <p class="form-hint">{{ $t('video.crop.description') }}</p>

    <div class="form-group">
      <label>{{ $t('video.crop.aspect_ratio') }}</label>
      <AppSelect v-model="aspectRatio" :options="aspectOptions" />
    </div>

    <div class="form-group">
      <label>{{ $t('video.crop.start_position') }}</label>
      <div class="coord-row">
        <div class="coord-field">
          <span class="coord-label">X</span>
          <input
            type="number" class="form-input" v-model.number="localX"
            :min="0" :max="maxX" placeholder="0"
            @change="commitX"
          />
        </div>
        <div class="coord-field">
          <span class="coord-label">Y</span>
          <input
            type="number" class="form-input" v-model.number="localY"
            :min="0" :max="maxY" placeholder="0"
            @change="commitY"
          />
        </div>
      </div>
    </div>

    <div class="form-group">
      <label>{{ $t('video.crop.crop_size') }}</label>
      <div class="coord-row">
        <div class="coord-field">
          <span class="coord-label">{{ $t('common.width') }}</span>
          <input
            type="number" class="form-input" v-model.number="localWidth"
            :min="2" :max="maxW" placeholder="px"
            @change="commitWidth"
          />
        </div>
        <div class="coord-field">
          <span class="coord-label">{{ $t('common.height') }}</span>
          <input
            type="number" class="form-input" v-model.number="localHeight"
            :min="2" :max="maxH" placeholder="px"
            :disabled="aspectRatio !== 'free'"
            @change="commitHeight"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

<style lang="scss" scoped>
.coord-row {
  display: flex;
  gap: 8px;
}

.coord-field {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;

  .coord-label {
    font-size: 0.8rem;
    color: var(--text-muted);
    white-space: nowrap;
    min-width: 12px;
  }

  .form-input {
    flex: 1;
    min-width: 0;
  }
}
</style>
