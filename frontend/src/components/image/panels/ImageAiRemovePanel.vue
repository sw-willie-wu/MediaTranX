<script setup lang="ts">
import { computed } from 'vue'
import AppRange from '@/components/common/AppRange.vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useToast } from '@/composables/useToast'
import type { MaskToolMode } from '@/composables/useCanvasMask'

const props = defineProps<{
  fileId: string | null
  currentFileName: string
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

const toast = useToast()
const { submitTask, isProcessing } = useSubmitTask()

const isDisabled = computed(() => !props.fileId || isProcessing.value)
const isLoading = computed(() => isProcessing.value)

const tools: { mode: MaskToolMode; icon: string; label: string }[] = [
  { mode: 'brush',   icon: 'bi-brush-fill',  label: '筆刷' },
  { mode: 'polygon', icon: 'bi-pentagon',     label: '多邊形' },
  { mode: 'bezier',  icon: 'bi-bezier2',      label: '曲線' },
  { mode: 'eraser',  icon: 'bi-eraser-fill', label: '橡皮擦' },
]

async function execute() {
  if (!props.fileId) return
  if (!props.hasMask()) {
    toast.show('請先在圖片上標記要移除的區域', { type: 'info', icon: 'bi-info-circle' })
    return
  }
  const maskData = props.getMask()
  if (!maskData) return

  const taskId = await submitTask(
    '/image/remove-object',
    { file_id: props.fileId, mask_data: maskData },
    'AI 物件移除',
    'image.remove_object',
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
}

defineExpose({ execute, isDisabled, isLoading })
</script>

<template>
  <div class="function-settings">
    <h6 class="settings-title">
      <i class="bi bi-magic me-2"></i>物件移除設定
    </h6>

    <p class="form-hint">在圖片上標記要移除的物件，AI 將自動填補背景</p>

    <div class="form-group">
      <label>選取工具</label>
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
        {{ toolMode === 'eraser' ? '橡皮擦大小' : '筆刷大小' }}
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
        <span>細</span><span>粗</span>
      </div>
      <p v-if="toolMode === 'brush'" class="form-hint">畫圓圈圍起來的區域會自動填滿</p>
    </div>

    <div v-else class="form-group">
      <p class="form-hint">
        點擊新增節點，靠近起點或雙擊封閉區域<br>
        右鍵撤回上一點 · <kbd>Esc</kbd> 全部取消
      </p>
    </div>

    <div class="form-group">
      <button class="btn-secondary" :disabled="isDisabled" @click="emit('clearMask')">
        <i class="bi bi-trash"></i>清除標記
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
