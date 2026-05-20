<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSubmitTask } from '@/composables/useSubmitTask'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  duration?: number
}>()

const emit = defineEmits<{
  submit: [taskId: string]
  'update:trimRange': [range: { start: number; end: number } | null]
}>()

const { t } = useI18n()
const { submitTask, isProcessing } = useSubmitTask()

const startTime = ref('00:00:00')
const endTime = ref('00:00:00')

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading  = computed(() => isProcessing.value)

// ── Time ↔ Ratio conversion ─────────────────────────────────────────────
function timeToSeconds(str: string): number {
  const parts = str.split(':').map(Number)
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  return parts[0] || 0
}

function secondsToTime(s: number): string {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

// ── Emit trim range when time inputs change ──────────────────────────────
let _skipSync = false

watch([startTime, endTime], () => {
  if (_skipSync || !props.duration) return
  const dur = props.duration
  const startRatio = Math.max(0, Math.min(1, timeToSeconds(startTime.value) / dur))
  const endRatio = Math.max(0, Math.min(1, timeToSeconds(endTime.value) / dur))
  if (endRatio > startRatio) {
    emit('update:trimRange', { start: startRatio, end: endRatio })
  }
})

// ── Receive trim range from waveform drag ────────────────────────────────
function onTrimRangeUpdate(range: { start: number; end: number }) {
  if (!props.duration) return
  _skipSync = true
  startTime.value = secondsToTime(range.start * props.duration)
  endTime.value = secondsToTime(range.end * props.duration)
  _skipSync = false
  emit('update:trimRange', range)
}

// ── Init default range when file/duration changes ────────────────────────
watch(() => props.duration, (dur) => {
  if (dur && dur > 0) {
    startTime.value = secondsToTime(dur * 0.2)
    endTime.value = secondsToTime(dur * 0.8)
    emit('update:trimRange', { start: 0.2, end: 0.8 })
  }
}, { immediate: true })

// ── Computed duration display ────────────────────────────────────────────
const selectionDuration = computed(() => {
  const start = timeToSeconds(startTime.value)
  const end = timeToSeconds(endTime.value)
  const diff = Math.max(0, end - start)
  const m = Math.floor(diff / 60)
  const s = Math.floor(diff % 60)
  return `${m}:${String(s).padStart(2, '0')}`
})

async function execute() {
  if (!props.fileId) return
  const taskId = await submitTask(
    '/audio/cut',
    {
      file_id: props.fileId,
      start_time: startTime.value,
      end_time: endTime.value,
    },
    t('audio.cut.task_label'),
    'audio.cut',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

// Clean up trim overlay when leaving
function clearTrim() {
  emit('update:trimRange', null)
}

defineExpose({ execute, isDisabled, isLoading, onTrimRangeUpdate, clearTrim })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title"><i class="bi bi-scissors me-2"></i>{{ $t('audio.cut.title') }}</h6>
    <p class="form-hint">{{ $t('audio.cut.description') }}</p>

    <div class="form-group">
      <label>{{ $t('audio.cut.start_time') }}</label>
      <input type="text" class="form-input" v-model="startTime" placeholder="00:00:00" />
    </div>

    <div class="form-group">
      <label>{{ $t('audio.cut.end_time') }}</label>
      <input type="text" class="form-input" v-model="endTime" placeholder="00:00:00" />
      <small class="form-hint">
        {{ $t('audio.cut.selection_duration') }} {{ selectionDuration }}
      </small>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
