<script setup lang="ts">
import { ref, computed } from 'vue'

interface SubFunction {
  id: string
  name: string
  icon: string
}

const props = defineProps<{
  title: string
  subFunctions: SubFunction[]
  currentFunction?: string
  hasFile?: boolean
  hasResult?: boolean
}>()

const emit = defineEmits<{
  (e: 'select-function', id: string): void
  (e: 'export'): void
}>()

// 預覽模式
type PreviewMode = 'original' | 'result' | 'compare'
const previewMode = ref<PreviewMode>('original')

const canShowResult = computed(() => props.hasResult)

function selectFunction(id: string) {
  emit('select-function', id)
}

function handleExport() {
  emit('export')
}
</script>

<template>
  <div class="tool-layout">
    <!-- 左側：子功能列表 -->
    <aside class="function-sidebar">
      <div class="function-list">
        <button
          v-for="fn in subFunctions"
          :key="fn.id"
          class="function-item"
          :class="{ active: currentFunction === fn.id }"
          @click="selectFunction(fn.id)"
        >
          <i :class="['bi', fn.icon]"></i>
          <span>{{ fn.name }}</span>
        </button>
      </div>
    </aside>

    <!-- 中間：預覽區域 -->
    <main class="preview-area">
      <!-- 預覽模式切換 -->
      <div class="preview-tabs" v-if="hasFile">
        <button
          class="preview-tab"
          :class="{ active: previewMode === 'original' }"
          @click="previewMode = 'original'"
        >
          原圖
        </button>
        <button
          class="preview-tab"
          :class="{ active: previewMode === 'result', disabled: !canShowResult }"
          :disabled="!canShowResult"
          @click="previewMode = 'result'"
        >
          成果
        </button>
        <button
          class="preview-tab"
          :class="{ active: previewMode === 'compare', disabled: !canShowResult }"
          :disabled="!canShowResult"
          @click="previewMode = 'compare'"
        >
          並排比對
        </button>
      </div>

      <!-- 預覽內容 -->
      <div class="preview-content">
        <slot name="preview" :mode="previewMode">
          <div class="preview-placeholder">
            <i class="bi bi-image"></i>
            <p>請選擇或拖曳檔案</p>
          </div>
        </slot>
      </div>
    </main>

    <!-- 右側：設定面板 -->
    <aside class="settings-panel">
      <div class="settings-content">
        <slot name="settings">
          <p class="text-muted">請選擇功能</p>
        </slot>
      </div>

      <!-- 匯出按鈕 -->
      <div class="export-section">
        <button
          class="export-btn"
          :disabled="!hasResult"
          @click="handleExport"
        >
          <i class="bi bi-download me-2"></i>
          匯出成果
        </button>
      </div>
    </aside>
  </div>
</template>

<style lang="scss" scoped>
.tool-layout {
  display: flex;
  height: calc(100vh - 40px);
  gap: 1rem;
  padding: 1rem;
}

// 左側子功能列表
.function-sidebar {
  position: relative;
  width: 180px;
  min-width: 180px;
  display: flex;
  flex-direction: column;
  padding: 1rem;
  padding-top: 0.5rem;
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
}

.function-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.function-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.7rem 1rem;
  background: transparent;
  border: none;
  border-radius: 8px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;

  i {
    font-size: 1.1rem;
    width: 22px;
  }

  span {
    font-size: 0.9rem;
  }

  &:hover {
    color: var(--text-primary);
    background: var(--panel-bg);
  }

  &.active {
    color: var(--text-primary);
    background: var(--panel-bg);
  }
}

// 中間預覽區
.preview-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  overflow: hidden;
}

.preview-tabs {
  display: flex;
  gap: 0.25rem;
  padding: 0.75rem;
  border-bottom: 1px solid var(--panel-border);
}

.preview-tab {
  padding: 0.4rem 0.75rem;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover:not(.disabled) {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
  }

  &.active {
    background: var(--panel-bg-active);
    color: var(--text-primary);
  }

  &.disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
}

.preview-content {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  overflow: auto;
}

.preview-placeholder {
  text-align: center;
  color: var(--text-muted);

  i {
    font-size: 4rem;
    margin-bottom: 1rem;
  }

  p {
    font-size: 1rem;
  }
}

// 右側設定面板
.settings-panel {
  width: 320px;
  min-width: 320px;
  display: flex;
  flex-direction: column;
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
}

.settings-content {
  flex: 1;
  padding: 1rem;
  overflow-y: auto;
  color: var(--text-primary);
}

.export-section {
  padding: 1rem;
  border-top: 1px solid var(--panel-border);
}

.export-btn {
  width: 100%;
  padding: 0.75rem 1rem;
  background: linear-gradient(135deg, var(--color-success) 0%, var(--color-success-hover) 100%);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.text-muted {
  color: var(--text-muted);
}
</style>
