<script setup lang="ts">
/**
 * image.upscale 參數元件（統一參數元件 spec §5；批 4 Task 4.4）。
 * UI 沿舊 components/image/panels/ImageUpscalePanel.vue（進階區 sharpen/face_fix/face
 * picker/face_restore_upscale，storage-key 沿舊 'image_upscale_advanced'）。
 *
 * 雙 composite（見 upscale.meta.ts 檔頭 id 型比對註解）：
 * - 'upscale_model'（covers:['model_id']）：token 就是 model.id 字面值（如
 *   'realesrgan-x4plus'），不需要 encode/decode——單欄位、直接映射。
 * - 'face_restore_model'（covers:['face_restore_model_id']）：同構，token=model.id。
 * 兩者 agent 欄位名沿舊 agentSchema：'upscale_model'/'face_restore_model'。
 *
 * maxScale 動態夾（沿舊 panel watch(maxScale)）：選中主模型的 max_scale??4，用 watch 把
 * params.scale 夾回上限——schema 的 min/max(2-4) 是靜態上限，實際 UI 上限依模型而定
 * （x2plus 系列 max_scale=2，其餘家族多為 4）。
 */
import { computed, onMounted, watch } from 'vue'
import AppToggle from '@/components/common/AppToggle.vue'
import AppRange from '@/components/common/AppRange.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import type { SelectOption } from '@/components/common/AppSelect.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import { useModelStore } from '@/stores/models'
import { usePersistedModel } from '@/composables/usePersistedModel'
import { useRegisterComposite } from '@/composables/useRegisterComposite'
import { META as UPSCALE_META } from './upscale.meta'

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

// ── 模型清單 ──────────────────────────────────────────────────────────────
const modelStore = useModelStore()

// fresh session 掛載時模型清單可能尚未載入過——沿其餘模型系元件慣例，onMounted 主動 ensureLoaded。
onMounted(() => {
  modelStore.ensureLoaded()
})

const upscaleModels = computed(() => modelStore.forPanel(modelStore.byCategory('upscale')))
const faceRestoreModels = computed(() => modelStore.forPanel(modelStore.byCategory('face_restore')))

const upscaleOptions = computed<SelectOption[]>(() =>
  upscaleModels.value.map((m) => ({
    value: m.id,
    label: m.label,
    badge: (m.downloaded ? 'ok' : 'err') as 'ok' | 'err',
  })),
)
const faceOptions = computed<SelectOption[]>(() =>
  faceRestoreModels.value.map((m) => ({
    value: m.id,
    label: m.label,
    badge: (m.downloaded ? 'ok' : 'err') as 'ok' | 'err',
  })),
)

const modelIdToken = computed(() => String(props.params.model_id ?? ''))
const faceModelIdToken = computed(() => String(props.params.face_restore_model_id ?? ''))

const selectedUpscaleModel = computed(() =>
  upscaleModels.value.find((m) => m.id === modelIdToken.value),
)

const maxScale = computed(() => selectedUpscaleModel.value?.max_scale ?? 4)
const scaleTicks = computed(() => Array.from({ length: maxScale.value - 1 }, (_, i) => i + 2))

// UI 上限收斂：schema min/max 是靜態 2-4，選中模型的實際上限可能更小（如 x2plus max_scale=2）。
// immediate:true——涵蓋掛載當下就選中一個低 max_scale 模型（如 seed/pipeline 帶入）的情形，
// 非僅「切模型後」才夾（沿舊 panel watch 精神，但補上初值 race）。
watch(
  maxScale,
  (max) => {
    const scale = Number(props.params.scale ?? 4)
    if (scale > max) commitPatch({ scale: max })
  },
  { immediate: true },
)

const selectedFaceFamily = computed(() => (faceModelIdToken.value.startsWith('gfpgan') ? 'gfpgan' : ''))

const persistedUpscaleToken = usePersistedModel('upscale_model', '', { enabled: props.context === 'tool' })
const persistedFaceToken = usePersistedModel('upscale_face_model', '', { enabled: props.context === 'tool' })

function onUpscaleModelChange(id: string) {
  commitPatch({ model_id: id })
  if (props.context === 'tool') persistedUpscaleToken.value = id
}
function onFaceModelChange(id: string) {
  commitPatch({ face_restore_model_id: id })
  if (props.context === 'tool') persistedFaceToken.value = id
}

const defaultModelId = String(UPSCALE_META.defaults().model_id ?? '')

// seed（掛載時 model_id 仍等於 defaults 才套用持久化值）＋fallback（清單載入後若目前 token
// 未對應任何已知選項，選第一個已下載模型）——沿 EnhanceParams/InterpolateParams pattern。
//
// upscale／face 兩個 setup 期同步 seed 收斂成單次 commitPatch（同構於 TranscribeParams.vue
// IMP-1 修復）：commitPatch 是 `{...props.params, ...patch}`，而 props.params 在同一個同步
// tick 內不會因前一個 emit 而更新（Vue prop 回流要等父層下一輪 render/flush）。若兩段各自呼叫
// commitPatch，後者一定基於「還沒套用前一段 patch」的 stale props.params，導致後段的 patch 把
// 前段剛寫入的欄位悄悄復原——使用者 localStorage 同時存有 upscale_model 與 upscale_face_model
// 時即會重現。修法：兩段各自只把要寫的欄位塞進共用 seed 物件，seeded flag 語意不變，最後一次性
// `if (Object.keys(seed).length) commitPatch(seed)`。
const seed: Record<string, unknown> = {}

let upscaleSeeded = false
if (props.context === 'tool' && persistedUpscaleToken.value && modelIdToken.value === defaultModelId) {
  seed.model_id = persistedUpscaleToken.value
  upscaleSeeded = true
}
watch(
  upscaleModels,
  (models) => {
    if (upscaleSeeded) return
    if (models.length === 0) return
    if (models.some((m) => m.id === modelIdToken.value)) return
    const first = models.find((m) => m.downloaded)
    if (first) {
      onUpscaleModelChange(first.id)
      upscaleSeeded = true
    }
  },
  { immediate: true },
)

// face model：無 defaults（schema 無 default 值），seed 判準改為「目前值為空」——沿舊
// ImageUpscalePanel 對 face 模型的 immediate watch 語意（`if (!selectedFaceModelId.value)`）。
let faceSeeded = false
if (props.context === 'tool' && persistedFaceToken.value && !faceModelIdToken.value) {
  seed.face_restore_model_id = persistedFaceToken.value
  faceSeeded = true
}

// 兩段 seed 蒐集完畢，單次提交（見上方 upscale 段落註解）。
if (Object.keys(seed).length) commitPatch(seed)

watch(
  faceRestoreModels,
  (models) => {
    if (faceSeeded) return
    if (models.length === 0) return
    if (faceModelIdToken.value) return
    const first = models.find((m) => m.downloaded)
    if (first) {
      onFaceModelChange(first.id)
      faceSeeded = true
    }
  },
  { immediate: true },
)

// ── composite 註冊（agent 欄位名沿舊 agentSchema：upscale_model/face_restore_model）───────
const registerComposite = useRegisterComposite()
registerComposite?.({
  name: 'upscale_model',
  covers: ['model_id'],
  options: () => upscaleOptions.value.map((o) => o.value),
  get: (p) => String(p.model_id ?? ''),
  set: (token) => ({ model_id: token }),
})
registerComposite?.({
  name: 'face_restore_model',
  covers: ['face_restore_model_id'],
  options: () => faceOptions.value.map((o) => o.value),
  get: (p) => String(p.face_restore_model_id ?? ''),
  set: (token) => ({ face_restore_model_id: token }),
})
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-arrows-angle-expand me-2"></i>{{ $t('image.upscale.title') }}</h6>
    <p class="form-hint">{{ $t('image.upscale.description') }}</p>

    <div class="form-group">
      <label>{{ $t('image.upscale.model') }}</label>
      <AppSelect
        :model-value="modelIdToken"
        :options="upscaleOptions"
        :disabled="modelStore.loading"
        :placeholder="$t('common.loading_info')"
        @update:model-value="onUpscaleModelChange"
      />
    </div>

    <div class="form-group">
      <label>
        {{ $t('image.upscale.scale') }}
        <span class="param-value">{{ Number(params.scale ?? 4) }}x</span>
      </label>
      <AppRange
        :model-value="Number(params.scale ?? 4)"
        :min="2"
        :max="maxScale"
        :step="1"
        :disabled="maxScale <= 2"
        @update:model-value="(v) => commitPatch({ scale: v })"
      />
      <div class="range-ticks">
        <span v-for="tick in scaleTicks" :key="tick">{{ tick }}x</span>
      </div>
    </div>

    <SettingsCollapsible storage-key="image_upscale_advanced">
      <div class="form-group">
        <AppToggle :model-value="params.sharpen === true" @update:model-value="(v) => commitPatch({ sharpen: v })">
          {{ $t('image.upscale.sharpen') }}
        </AppToggle>
        <small class="form-hint">{{ $t('image.upscale.sharpen_hint') }}</small>
      </div>

      <div class="form-group">
        <AppToggle :model-value="params.face_fix === true" @update:model-value="(v) => commitPatch({ face_fix: v })">
          {{ $t('image.upscale.face_restore') }}
        </AppToggle>
        <small class="form-hint">{{ $t('image.upscale.face_restore_hint') }}</small>

        <div v-if="params.face_fix === true" class="sub-params">
          <AppSelect
            :model-value="faceModelIdToken"
            :options="faceOptions"
            :placeholder="$t('common.select_function')"
            @update:model-value="onFaceModelChange"
          />

          <template v-if="selectedFaceFamily === 'gfpgan'">
            <label class="sub-label">
              {{ $t('image.upscale.face_scale') }}
              <span class="param-value">{{ Number(params.face_restore_upscale ?? 2) }}x</span>
            </label>
            <AppRange
              :model-value="Number(params.face_restore_upscale ?? 2)"
              :min="1"
              :max="4"
              :step="1"
              @update:model-value="(v) => commitPatch({ face_restore_upscale: v })"
            />
            <div class="range-ticks"><span>1x</span><span>4x</span></div>
          </template>
        </div>
      </div>
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
