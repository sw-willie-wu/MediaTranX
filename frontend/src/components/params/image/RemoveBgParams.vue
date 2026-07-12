<script setup lang="ts">
/**
 * image.remove_bg 參數元件（統一參數元件 spec §5；批 4 Task 4.3——最簡單的標準遷移）。
 * UI 沿舊 components/image/panels/ImageRemoveBgPanel.vue：單一 mode AppSelect。
 * 契約：params/context/fileInfo in、update:params out——host 統一收發，本元件不呼叫 API。
 *
 * 單一 enum 欄位、無多欄位互斥/canvas 橋接，直接用 computed get/set 綁 AppSelect
 * （沿 audio/VolumeParams.vue 慣例：無文字輸入框競態問題時不需要 CutParams.vue 的
 * one-shot lastEmitted pattern，AppSelect 每次選擇都是完整、離散的使用者意圖）。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'

const props = defineProps<{
  params: Record<string, unknown>
  context: 'tool' | 'pipeline'
  fileInfo?: Record<string, unknown> | null
}>()
const emit = defineEmits<{
  'update:params': [Record<string, unknown>]
}>()

const { t } = useI18n()

const mode = computed<string>({
  get: () => (typeof props.params.mode === 'string' ? props.params.mode : 'auto'),
  set: (v) => emit('update:params', { ...props.params, mode: v }),
})

const modeOptions = computed(() => [
  { value: 'auto',    label: t('image.remove_bg.auto') },
  { value: 'person',  label: t('image.remove_bg.person') },
  { value: 'product', label: t('image.remove_bg.product') },
  { value: 'animal',  label: t('image.remove_bg.animal') },
  { value: 'anime',   label: t('image.remove_bg.anime') },
])
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-eraser-fill me-2"></i>{{ $t('image.remove_bg.title') }}
    </h6>
    <p class="form-hint">{{ $t('image.remove_bg.description') }}</p>

    <div class="form-group">
      <label>{{ $t('image.remove_bg.mode') }}</label>
      <AppSelect v-model="mode" :options="modeOptions" />
      <small class="form-hint">{{ $t('image.remove_bg.auto_hint') }}</small>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
