<script setup lang="ts">
/**
 * video.interpolate 參數元件（統一參數元件 spec §5；批 2 Task 2.3）。
 * UI 沿舊 components/video/panels/VideoInterpolatePanel.vue。
 *
 * model picker 用單欄 composite（covers:['model']）而非讓 host 直接用 schema 的 'model'
 * enum 欄位——schema.model 是靜態 enum（僅 v4.26，見 interpolate.meta.ts 檔頭），但 picker
 * 需要即時反映 modelStore 下載狀態（badge），composite 的 options() 提供這份即時清單
 * （同 TranslateParams.vue pattern，唯此處單欄、無 remote 分支，邏輯簡化）。
 *
 * 本元件所有顯示值皆為 props.params 的直接響應式衍生（無本地編輯緩衝 ref）——AppSelect/
 * AppRange 選擇即時 commit，故不需 CutParams/TranscodeParams 的 one-shot lastEmitted 判別
 * （該 pattern 是為了保護「使用者輸入中」的本地文字狀態不被外部寫入打斷；本元件無此狀態，
 * 沿 ExtractAudioParams.vue 的簡化模式）。
 */
import { computed, inject, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import type { SelectOption } from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import { useModelStore } from '@/stores/models'
import { usePersistedModel } from '@/composables/usePersistedModel'
import type { AgentCompositeField } from '../types'
import { META as INTERPOLATE_META } from './interpolate.meta'

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

// ── model picker（RIFE 單一家族，token=純 variant 字串）─────────────────────
const modelStore = useModelStore()

// fresh session 掛載時模型清單可能尚未載入過——舊 VideoInterpolatePanel 與其他模型系 panel
// 皆在 onMounted 主動 ensureLoaded，否則 picker 顯示空清單且 disabled。
onMounted(() => {
  modelStore.ensureLoaded()
})

const modelOptions = computed<SelectOption[]>(() =>
  modelStore.forPanel(modelStore.byCategory('interpolate')).map((m) => ({
    value: m.variant,
    label: m.label,
    badge: (m.downloaded ? 'ok' : 'err') as 'ok' | 'err',
  })),
)

const modelToken = computed(() => String(props.params.model ?? ''))

const persistedToken = usePersistedModel('interpolate_model', 'v4.26', { enabled: props.context === 'tool' })

function onModelTokenChange(token: string) {
  commitPatch({ model: token })
  if (props.context === 'tool') persistedToken.value = token
}

const defaultModel = String(INTERPOLATE_META.defaults().model ?? '')

// seed：僅在掛載時 model 仍等於 defaults（使用者/host 尚未動過模型選擇）才套用持久化值——
// 沿 TranslateParams.vue 的 seed pattern（單欄無 remote 分支，邏輯簡化，見檔頭註解）。
if (props.context === 'tool' && persistedToken.value && modelToken.value === defaultModel) {
  commit({ ...props.params, model: persistedToken.value })
}

// ── composite 註冊（單欄，為 model picker 提供即時 options；覆蓋 schema 的靜態 'model' enum）──
const registerComposite = inject<(c: AgentCompositeField) => () => void>('registerComposite')
registerComposite?.({
  name: 'model',
  covers: ['model'],
  options: () => modelOptions.value.map((o) => o.value),
  get: (p) => String(p.model ?? ''),
  set: (token) => ({ model: token }),
})

// ── mode / target_fps ────────────────────────────────────────────────────
const modeOptions = computed(() => [
  { value: '2x', label: t('video.interpolate.mode_2x') },
  { value: '4x', label: t('video.interpolate.mode_4x') },
  { value: 'custom', label: t('video.interpolate.mode_custom') },
])

const mode = computed(() => String(props.params.mode ?? '2x'))
const isCustomMode = computed(() => mode.value === 'custom')

const sourceFps = computed(() => {
  const fps = props.fileInfo?.fps
  return typeof fps === 'number' ? fps : 0
})

const targetFps = computed(() => Number(props.params.target_fps ?? 60))

const outputFps = computed(() => {
  if (isCustomMode.value) return targetFps.value
  if (mode.value === '4x') return sourceFps.value * 4
  return sourceFps.value * 2
})

// UI 提示用（沿舊 panel 顯示邏輯）——host 端目前無法把 fileInfo 帶進 meta.validate()，
// 故此警示僅為視覺提示，不再如舊 panel 那樣阻擋 execute（concern 見報告）。
const fpsWarning = computed(() => isCustomMode.value && targetFps.value <= sourceFps.value)

function onModeChange(v: string) {
  commitPatch({ mode: v })
}
function onTargetFpsChange(v: number) {
  commitPatch({ target_fps: v })
}

// ── output_format / video_codec ──────────────────────────────────────────
const formatOptions = computed(() => [
  { value: 'mp4', label: 'MP4' },
  { value: 'mkv', label: 'MKV' },
  { value: 'webm', label: 'WebM' },
  { value: 'mov', label: 'MOV' },
])
const codecOptions = computed(() => [
  { value: 'h264', label: 'H.264' },
  { value: 'h265', label: 'H.265 (HEVC)' },
  { value: 'vp9', label: 'VP9' },
  { value: 'av1', label: 'AV1' },
])
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-speedometer2 me-2"></i>{{ $t('video.interpolate.title') }}</h6>
    <p class="form-hint">{{ $t('video.interpolate.description') }}</p>

    <div class="form-group">
      <label>{{ $t('video.interpolate.model') }}</label>
      <AppSelect :modelValue="modelToken" :options="modelOptions" @update:modelValue="onModelTokenChange" />
    </div>

    <div class="form-group">
      <label>{{ $t('video.interpolate.mode') }}</label>
      <AppSelect :modelValue="mode" :options="modeOptions" @update:modelValue="onModeChange" />
    </div>

    <div v-if="isCustomMode" class="form-group">
      <label>{{ $t('video.interpolate.target_fps') }}: {{ targetFps }}</label>
      <AppRange
        :modelValue="targetFps"
        :min="Math.ceil(sourceFps) + 1 || 2"
        :max="240"
        :step="1"
        @update:modelValue="onTargetFpsChange"
      />
      <small v-if="fpsWarning" class="form-hint text-danger">{{ $t('video.interpolate.fps_warning') }}</small>
    </div>

    <div v-if="sourceFps > 0" class="form-group fps-info">
      <span>{{ $t('video.interpolate.current_fps') }}: <strong>{{ sourceFps.toFixed(1) }}</strong></span>
      <span class="fps-arrow">→</span>
      <span>{{ $t('video.interpolate.output_fps') }}: <strong>{{ outputFps.toFixed(1) }}</strong></span>
    </div>

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect
        :modelValue="String(params.output_format ?? 'mp4')"
        :options="formatOptions"
        @update:modelValue="(v) => commitPatch({ output_format: v })"
      />
    </div>

    <SettingsCollapsible storage-key="video_interpolate_advanced">
      <div class="form-group">
        <label>{{ $t('video.interpolate.video_codec') }}</label>
        <AppSelect
          :modelValue="String(params.video_codec ?? 'h264')"
          :options="codecOptions"
          @update:modelValue="(v) => commitPatch({ video_codec: v })"
        />
      </div>
    </SettingsCollapsible>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

<style lang="scss" scoped>
.fps-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: var(--bg-secondary);
  border-radius: 6px;
  font-size: 0.875rem;
}
.fps-arrow {
  color: var(--color-primary);
  font-weight: bold;
}
.text-danger {
  color: var(--color-danger);
}
</style>
