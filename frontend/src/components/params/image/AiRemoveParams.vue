<script setup lang="ts">
/**
 * image.remove_object 工具列參數元件（統一參數元件 spec §5；批 4 Task 4.5 Part C——最小
 * 侵入拆分，照 audio/MidiExportParams.vue 模式）。
 *
 * ⭐邊界（見 batch4-recon.md §7）：remove_object 唯一送後端的「參數」是 mask_data（canvas
 * 匯出的 base64 PNG）——不可拆、仍完全由 ImageAiRemovePanel.vue 的 execute/guard/mask 流程
 * 管理（一行不動）。brushSize/toolMode 是 canvas 互動狀態，非後端請求欄位，因此本檔：
 * - 不建 meta.ts（無對映的 Pydantic request 純量欄位可描述）
 * - 不進 PARAM_COMPONENTS/METAS/registry（互動工具，非標準三步同構對象）
 * - 不採用其他 Params.vue 的 params/context/fileInfo 契約（那個契約描述的是「後端請求欄位
 *   的 dict」，brushSize/toolMode 不是請求欄位）——改用受控 v-model prop 直接對映
 *   ImageAiRemovePanel.vue 自己的既有 props（brushSize/toolMode），純粹是把工具列這塊
 *   template 從殼裡搬出來的顯示層重構。
 *
 * 只抽取工具列 UI（toolMode 選擇器＋brush/eraser slider 或 polygon/bezier hint＋清除鈕）；
 * 標題/描述、execute()/guardModelReady()/hasMask()/getMask() 等執行流程留在
 * ImageAiRemovePanel.vue 不動。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppRange from '@/components/common/AppRange.vue'
import type { MaskToolMode } from '@/composables/useCanvasMask'

const props = defineProps<{
  brushSize: number
  toolMode: MaskToolMode
  isDisabled?: boolean
}>()

const emit = defineEmits<{
  'update:brushSize': [value: number]
  'update:toolMode': [value: MaskToolMode]
  clearMask: []
}>()

const { t } = useI18n()

const tools = computed<{ mode: MaskToolMode; icon: string; label: string }[]>(() => [
  { mode: 'brush',   icon: 'bi-brush-fill',  label: t('image.remove_object.brush') },
  { mode: 'polygon', icon: 'bi-pentagon',     label: t('image.remove_object.polygon') },
  { mode: 'bezier',  icon: 'bi-bezier2',      label: t('image.remove_object.bezier') },
  { mode: 'eraser',  icon: 'bi-eraser-fill',  label: t('image.remove_object.eraser') },
])
</script>

<template>
  <div class="form-group">
    <label>{{ $t('image.remove_object.tools') }}</label>
    <div class="mask-tool-selector">
      <button
        v-for="tool in tools"
        :key="tool.mode"
        class="mask-tool-btn"
        :class="{ 'is-active': toolMode === tool.mode }"
        :data-tooltip="tool.label"
        @click="emit('update:toolMode', tool.mode)"
      >
        <i class="bi" :class="tool.icon"></i>
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
</style>
