<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSubmitTask } from '@/composables/useSubmitTask'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
}>()

const emit = defineEmits<{
  submit: [taskId: string]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()

const pages = ref('')

watch(() => props.fileId, () => { pages.value = '' })

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

async function execute() {
  if (!props.fileId) return
  const body: Record<string, any> = {
    file_id: props.fileId,
    pages: pages.value.trim(),
  }
  const taskId = await submitTask('/document/split', body, t('document.split.task_label'), 'document.split', props.currentFileName)
  if (taskId) emit('submit', taskId)
}

function getParams() {
  const body: Record<string, any> = {
    pages: pages.value.trim(),
  }
  return body
}

defineExpose({ execute, isDisabled, isLoading, getParams })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-layout-split me-2"></i>{{ $t('document.split.title') }}</h6>
    <p class="form-hint">{{ $t('document.split.description') }}</p>

    <!-- 頁碼範圍 -->
    <div class="form-group">
      <label>{{ $t('document.split.page_range') }}</label>
      <input
        v-model="pages"
        class="form-input"
        type="text"
        :placeholder="$t('document.split.range_example')"
      />
      <small class="form-hint">{{ $t('document.split.range_hint', { example: '1-3,5,8-10' }) }}</small>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
