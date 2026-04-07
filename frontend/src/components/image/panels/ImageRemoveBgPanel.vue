<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppSelect from '@/components/common/AppSelect.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useModelGuard } from '@/composables/useModelGuard'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()
const { guardModelReady } = useModelGuard()

const removeBgMode = ref('auto')
const removeBgModes = computed(() => [
  { value: 'auto',    label: t('image.remove_bg.auto') },
  { value: 'person',  label: t('image.remove_bg.person') },
  { value: 'product', label: t('image.remove_bg.product') },
  { value: 'animal',  label: t('image.remove_bg.animal') },
  { value: 'anime',   label: t('image.remove_bg.anime') },
])

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

function getParams(): Record<string, unknown> {
  return {
    mode: removeBgMode.value,
  }
}

async function execute() {
  if (!await guardModelReady(true, 'image')) return
  if (!props.fileId) return
  const taskId = await submitTask(
    '/image/remove-bg',
    { file_id: props.fileId, ...getParams() },
    t('image.remove_bg.task_label'),
    'image.remove_bg',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading, getParams })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-eraser-fill me-2"></i>{{ $t('image.remove_bg.title') }}
    </h6>
    <p class="form-hint">{{ $t('image.remove_bg.description') }}</p>

    <div class="form-group">
      <label>{{ $t('image.remove_bg.mode') }}</label>
      <AppSelect v-model="removeBgMode" :options="removeBgModes" />
      <small class="form-hint">{{ $t('image.remove_bg.auto_hint') }}</small>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
