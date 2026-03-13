<script setup lang="ts">
import { ref, computed } from 'vue'
import AppRange from '@/components/common/AppRange.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { submitTask, isProcessing } = useSubmitTask()

const mode = ref<'adjust' | 'normalize'>('adjust')
const volumeDb = ref(0)

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

const volumeLabel = computed(() => {
  if (volumeDb.value === 0) return '±0 dB（原始）'
  return volumeDb.value > 0 ? `+${volumeDb.value} dB` : `${volumeDb.value} dB`
})

async function execute() {
  if (!props.fileId) return
  const taskId = await submitTask(
    '/audio/volume',
    {
      file_id: props.fileId,
      volume_db: mode.value === 'normalize' ? 0 : volumeDb.value,
      normalize: mode.value === 'normalize',
    },
    mode.value === 'normalize' ? '音量正規化' : '音量調整',
    'audio.volume',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-volume-up-fill me-2"></i>音量調整設定</h6>
    <p class="form-hint">手動調整音量倍率，或自動正規化至標準響度。</p>

    <div class="form-group">
      <label>模式</label>
      <div class="btn-choice-group">
        <button class="btn-choice" :class="{ 'is-active': mode === 'adjust' }" @click="mode = 'adjust'">
          手動調整
        </button>
        <button class="btn-choice" :class="{ 'is-active': mode === 'normalize' }" @click="mode = 'normalize'">
          響度正規化
        </button>
      </div>
    </div>

    <template v-if="mode === 'adjust'">
      <div class="form-group">
        <label>音量 <span class="param-value">{{ volumeLabel }}</span></label>
        <AppRange v-model="volumeDb" :min="-20" :max="20" :step="1" />
      </div>
    </template>

    <small v-else class="form-hint">
      使用 EBU R128 響度標準自動正規化，讓音量達到一致水準。
    </small>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

