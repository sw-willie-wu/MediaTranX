<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import AppRange from '@/components/common/AppRange.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useToast } from '@/composables/useToast'
import { useModelStore } from '@/stores/models'
import { useModelGuard } from '@/composables/useModelGuard'
import type { MaskToolMode } from '@/composables/useCanvasMask'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
  imageInfo: { format?: string } | null
  brushSize: number
  toolMode: MaskToolMode
  getMask: () => string | null
  hasMask: () => boolean
}>()

const emit = defineEmits<{
  submit: [taskId: string]
  'update:brushSize': [value: number]
  'update:toolMode': [value: MaskToolMode]
  clearMask: []
}>()

const { t } = useI18n()
const toast = useToast()
const { submitTask, isProcessing } = useSubmitTask()
const modelStore = useModelStore()
const { guardModelReady } = useModelGuard()

const isAnimated = computed(() => {
  const fmt = props.imageInfo?.format?.toUpperCase()
  return fmt === 'GIF' || fmt === 'APNG'
})
const isDisabled = computed(() => !props.fileId || isProcessing.value || isAnimated.value)
const isLoading = computed(() => isProcessing.value)

const tools = computed<{ mode: MaskToolMode; icon: string; label: string }[]>(() => [
  { mode: 'brush',   icon: 'bi-brush-fill',  label: t('image.remove_object.brush') },
  { mode: 'polygon', icon: 'bi-pentagon',     label: t('image.remove_object.polygon') },
  { mode: 'bezier',  icon: 'bi-bezier2',      label: t('image.remove_object.bezier') },
  { mode: 'eraser',  icon: 'bi-eraser-fill',  label: t('image.remove_object.eraser') },
])

async function execute() {
  const segmentDownloaded = modelStore.byCategory('segment').some(m => m.downloaded)
  if (!await guardModelReady(segmentDownloaded, 'image')) return
  if (!props.fileId) return
  if (!props.hasMask()) {
    toast.show(t('toast.mark_area_first'), { type: 'info', icon: 'bi-info-circle' })
    return
  }
  const maskData = props.getMask()
  if (!maskData) return

  const taskId = await submitTask(
    '/image/remove-object',
    { file_id: props.fileId, mask_data: maskData },
    t('image.remove_object.task_label'),
    'image.remove_object',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

onMounted(() => modelStore.ensureLoaded())

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-magic me-2"></i>{{ $t('image.remove_object.title') }}
    </h6>

    <p class="form-hint">{{ $t('image.remove_object.description') }}</p>

    <div class="form-group">
      <label>{{ $t('image.remove_object.tools') }}</label>
      <div class="mask-tool-selector">
        <button
          v-for="t in tools"
          :key="t.mode"
          class="mask-tool-btn"
          :class="{ 'is-active': toolMode === t.mode }"
          :data-tooltip="t.label"
          @click="emit('update:toolMode', t.mode)"
        >
          <i class="bi" :class="t.icon"></i>
        </button>
      </div>
    </div>

    <div v-if="toolMode === 'brush' || toolMode === 'eraser'" class="form-group">
      <label>
        {{ toolMode === 'eraser' ? $t('image.remove_object.eraser_size') : $t('image.remove_object.brush_size') }}
        <span class="param-value">{{ brushSize }}</span>
      </label>
      <AppRange
        :model-value="brushSize"
        :min="1"
        :max="80"
        :step="1"
        @update:model-value="emit('update:brushSize', $event)"
      />
      <div class="range-ticks">
        <span>{{ $t('image.remove_object.thin') }}</span><span>{{ $t('image.remove_object.thick') }}</span>
      </div>
      <p v-if="toolMode === 'brush'" class="form-hint">{{ $t('image.remove_object.brush_hint') }}</p>
    </div>

    <div v-else class="form-group">
      <p class="form-hint">
        {{ $t('image.remove_object.polygon_hint') }}<br>
        {{ $t('image.remove_object.polygon_controls', { esc: 'Esc' }) }}
      </p>
    </div>

    <div class="form-group">
      <button class="btn-secondary" :disabled="isDisabled" @click="emit('clearMask')">
        <i class="bi bi-trash"></i>{{ $t('image.remove_object.clear') }}
      </button>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

<style lang="scss" scoped>
.mask-tool-selector {
  display: flex;
  gap: 4px;
}

.mask-tool-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    border-color: var(--panel-border-hover);
    color: var(--text-primary);
  }

  &.is-active {
    background: rgba(168, 156, 200, 0.15);
    border-color: var(--color-accent);
    color: var(--color-accent);
  }

  i { font-size: 1rem; }

  // Tooltip — 下方浮出
  &::after {
    content: attr(data-tooltip);
    position: absolute;
    top: calc(100% + 6px);
    left: 50%;
    transform: translateX(-50%);
    padding: 3px 8px;
    background: var(--panel-bg-active);
    border: 1px solid var(--panel-border);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 0.72rem;
    white-space: nowrap;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s ease;
  }

  &:hover::after { opacity: 1; }
}

kbd {
  display: inline-block;
  padding: 1px 6px;
  font-size: 0.72rem;
  font-family: inherit;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 6px;
  color: var(--text-secondary);
}
</style>
