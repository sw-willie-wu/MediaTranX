<script setup lang="ts">
/**
 * video.enhance 參數元件（統一參數元件 spec §5；批 2 Task 2.3）。
 * UI 沿舊 components/video/panels/VideoEnhancePanel.vue。
 *
 * variant picker 用 composite（name:'model', covers:['model','variant']）——沿舊
 * VideoEnhancePanel.agentSchema 把 agent 欄位名 'model' 綁到 variant 值（'model' 後端欄位
 * 恆送 'realesrgan'，非使用者可選項）；covers 兩欄，set() 同時把兩欄一起寫回，符合
 * common-constraints「composite covers 必須涵蓋所有被 token 取代的後端欄位」。
 *
 * 本元件所有顯示值皆為 props.params 的直接響應式衍生（無本地編輯緩衝 ref），不需
 * one-shot lastEmitted 判別（沿 InterpolateParams.vue／ExtractAudioParams.vue 的簡化模式）。
 */
import { computed, onMounted } from 'vue'
import AppSelect from '@/components/common/AppSelect.vue'
import type { SelectOption } from '@/components/common/AppSelect.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import { useModelStore } from '@/stores/models'
import { usePersistedModel } from '@/composables/usePersistedModel'
import { useRegisterComposite } from '@/composables/useRegisterComposite'
import { META as ENHANCE_META } from './enhance.meta'

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

// ── variant picker（realesrgan 單一家族，token=純 variant 字串）────────────
const modelStore = useModelStore()

// fresh session 掛載時模型清單可能尚未載入過——舊 VideoEnhancePanel 與其他模型系 panel
// 皆在 onMounted 主動 ensureLoaded，否則 picker 顯示空清單且 disabled。
onMounted(() => {
  modelStore.ensureLoaded()
})

const variantOptions = computed<SelectOption[]>(() => {
  const items = [
    ...modelStore.forPanel(modelStore.byCategory('upscale')),
    ...modelStore.forPanel(modelStore.byCategory('video_enhance')),
  ]
  return items
    .filter((m) => m.family === 'realesrgan')
    .map((m) => ({
      value: m.variant,
      label: m.label,
      badge: (m.downloaded ? 'ok' : 'err') as 'ok' | 'err',
    }))
})

const variantToken = computed(() => String(props.params.variant ?? ''))

const persistedToken = usePersistedModel('enhance_model', 'x4plus', { enabled: props.context === 'tool' })

function onVariantChange(token: string) {
  commitPatch({ variant: token, model: 'realesrgan' })
  if (props.context === 'tool') persistedToken.value = token
}

const defaultVariant = String(ENHANCE_META.defaults().variant ?? '')

// seed：僅在掛載時 variant 仍等於 defaults（使用者/host 尚未動過模型選擇）才套用持久化值——
// 沿 InterpolateParams.vue／TranslateParams.vue 的 seed pattern。
if (props.context === 'tool' && persistedToken.value && variantToken.value === defaultVariant) {
  commit({ ...props.params, variant: persistedToken.value, model: 'realesrgan' })
}

// ── composite 註冊：agent 欄位名沿用舊 panel 的 'model'，實際覆蓋 model+variant 兩欄 ──────
const registerComposite = useRegisterComposite()
registerComposite?.({
  name: 'model',
  covers: ['model', 'variant'],
  options: () => variantOptions.value.map((o) => o.value),
  get: (p) => String(p.variant ?? ''),
  set: (token) => ({ variant: token, model: 'realesrgan' }),
})

// ── 輸出解析度預覽（沿舊 panel：scale 由 variant 含 'x2' 決定 2 或 4）───────────────────
const scale = computed(() => (variantToken.value.includes('x2') ? 2 : 4))

const outputResolution = computed(() => {
  const w = props.fileInfo?.width
  const h = props.fileInfo?.height
  if (typeof w !== 'number' || typeof h !== 'number') return ''
  return `${w}×${h} → ${w * scale.value}×${h * scale.value}`
})

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
    <h6 class="settings-title"><i class="bi bi-stars me-2"></i>{{ $t('video.enhance.title') }}</h6>
    <p class="form-hint">{{ $t('video.enhance.description') }}</p>

    <div class="form-group">
      <label>{{ $t('video.enhance.model') }}</label>
      <AppSelect :modelValue="variantToken" :options="variantOptions" @update:modelValue="onVariantChange" />
    </div>

    <div v-if="outputResolution" class="form-group resolution-preview">
      <label>{{ $t('video.enhance.output_resolution') }}</label>
      <span class="resolution-text">{{ outputResolution }}</span>
    </div>

    <div class="form-group">
      <label>{{ $t('common.output_format') }}</label>
      <AppSelect
        :modelValue="String(params.output_format ?? 'mp4')"
        :options="formatOptions"
        @update:modelValue="(v) => commitPatch({ output_format: v })"
      />
    </div>

    <SettingsCollapsible storage-key="video_enhance_advanced">
      <div class="form-group">
        <label>{{ $t('video.enhance.video_codec') }}</label>
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
.resolution-preview {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.resolution-text {
  font-size: 0.875rem;
  color: var(--color-primary);
  font-weight: 500;
}
</style>
