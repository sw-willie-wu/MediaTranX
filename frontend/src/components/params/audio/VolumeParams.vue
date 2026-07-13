<script setup lang="ts">
/**
 * audio.volume 參數元件（統一參數元件 spec §5；批 3 Task 3.1）。
 * UI 沿舊 components/audio/panels/AudioVolumePanel.vue。
 *
 * mode（adjust/normalize）是 UI 便利衍生：params.normalize 反推顯示，不另存本地狀態
 * （spec 決策——unified 元件的狀態單一事實來源是 params，不維護平行的私有 mode ref）；
 * 模式切換保留 params.volume_db（沿舊 panel 行為），normalize 送出時歸零由
 * volume.meta.ts 的 buildSubmit 單點處理。
 *
 * AppRange 滑桿沿舊 UI 收斂為 ±20（後端/schema 容許到 ±30，agent/pipeline 可設更大值，
 * UI 僅收斂顯示範圍，不影響 setField 的合法範圍）。
 *
 * gainPreview 出向：watch volume_db/mode → emit update:gainPreview（10^(db/20)，normalize
 * 恆 1）——沿 CropParams.vue 的 $attrs/emit 透傳先例，經 ToolParamHost 單根元件 attrs
 * fallthrough 穿透到 AudioView（host 未宣告此 prop/事件）。
 */
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppRange from '@/components/common/AppRange.vue'

const { t } = useI18n()

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
}>()
const emit = defineEmits<{
  'update:params': [Record<string, unknown>]
  'update:gainPreview': [gain: number]
}>()

function commitPatch(patch: Record<string, unknown>) {
  emit('update:params', { ...props.params, ...patch })
}

const mode = computed<'adjust' | 'normalize'>(() =>
  props.params.normalize === true ? 'normalize' : 'adjust',
)
const volumeDb = computed(() => Number(props.params.volume_db ?? 0))

function setMode(next: 'adjust' | 'normalize') {
  // volume_db 保留使用者滑桿值（切回 adjust 不遺失）；normalize 送出時歸零由 buildSubmit 處理
  commitPatch({ normalize: next === 'normalize' })
}

function onVolumeChange(v: number) {
  commitPatch({ volume_db: v })
}

const volumeLabel = computed(() => {
  const db = volumeDb.value
  if (db === 0) return t('audio.volume.original')
  return db > 0 ? `+${db} dB` : `${db} dB`
})

// dB → linear gain: 10^(dB/20)；normalize 模式恆 1（沿舊 panel：normalize 不做增益預覽縮放）
watch(
  () => [volumeDb.value, mode.value] as const,
  ([db, m]) => {
    emit('update:gainPreview', m === 'normalize' ? 1 : Math.pow(10, db / 20))
  },
  { immediate: true },
)
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-volume-up-fill me-2"></i>{{ $t('audio.volume.title') }}</h6>
    <p class="form-hint">{{ $t('audio.volume.description') }}</p>

    <div class="form-group">
      <label>{{ $t('audio.volume.mode') }}</label>
      <div class="btn-choice-group">
        <button class="btn-choice" :class="{ 'is-active': mode === 'adjust' }" @click="setMode('adjust')">
          {{ $t('audio.volume.manual') }}
        </button>
        <button class="btn-choice" :class="{ 'is-active': mode === 'normalize' }" @click="setMode('normalize')">
          {{ $t('audio.volume.normalize') }}
        </button>
      </div>
    </div>

    <template v-if="mode === 'adjust'">
      <div class="form-group">
        <label>{{ $t('audio.volume.volume') }} <span class="param-value">{{ volumeLabel }}</span></label>
        <AppRange :modelValue="volumeDb" :min="-20" :max="20" :step="1" @update:modelValue="onVolumeChange" />
      </div>
    </template>

    <small v-else class="form-hint">
      {{ $t('audio.volume.normalize_hint') }}
    </small>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
