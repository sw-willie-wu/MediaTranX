<script setup lang="ts">
import IconMinimize from './icons/IconMinimize.vue'
import IconMaximize from './icons/IconMaximize.vue'
import IconRestore from './icons/IconRestore.vue'
import IconClose from './icons/IconClose.vue'
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTitlebar } from '@/composables/useTitlebar'

const route = useRoute()
const isMaximized = ref(false)
const { t } = useI18n()
const { activeFileName, canUndo, canRedo, canSave, canSaveAs, undo, redo, save, saveAs, extraActions } = useTitlebar()

const isToolPage = computed(() => !!toolTitleKeys[route.path])

// 工具頁路徑
const toolTitleKeys: Record<string, string> = {
  '/image': 'titlebar.image',
  '/video': 'titlebar.video',
  '/audio': 'titlebar.audio',
  '/document': 'titlebar.document',
}

// 非工具頁路徑
const pageTitleKeys: Record<string, string> = {
  '/history': 'titlebar.history',
  '/tasks': 'titlebar.tasks',
  '/settings': 'titlebar.settings',
}

const pageTitle = computed(() => {
  const toolKey = toolTitleKeys[route.path]
  if (toolKey) {
    const toolName = t(toolKey)
    return activeFileName.value ? `${toolName} - ${activeFileName.value}` : toolName
  }
  const pageKey = pageTitleKeys[route.path]
  return pageKey ? t(pageKey) : ''
})

function minimize() {
  window.electron?.minimize()
}

function toggleFullScreen() {
  window.electron?.maximize()
}

function close() {
  window.electron?.close()
}

onMounted(async () => {
  if (window.electron) {
    isMaximized.value = await window.electron.isMaximized()
    window.electron.onMaximizeChange((val) => {
      isMaximized.value = val
    })
  }
})
</script>

<template>
  <div class="titlebar pywebview-drag-region">
    <div class="titlebar-left">
      <template v-if="isToolPage">
        <button class="titlebar-action" :disabled="!canUndo" :data-tooltip="$t('titlebar.undo')" @click="undo">
          <i class="bi bi-arrow-return-left flip-v"></i>
        </button>
        <button class="titlebar-action" :disabled="!canRedo" :data-tooltip="$t('titlebar.redo')" @click="redo">
          <i class="bi bi-arrow-return-right flip-v"></i>
        </button>
        <button class="titlebar-action" :class="{ 'is-highlighted': canSaveAs }" :disabled="!canSaveAs" :data-tooltip="$t('titlebar.save_as')" @click="saveAs">
          <i class="bi bi-floppy"></i>
        </button>
        <div v-if="extraActions.length" class="titlebar-separator"></div>
        <button
          v-for="action in extraActions"
          :key="action.id"
          class="titlebar-action"
          :class="{ 'is-active': action.active }"
          :disabled="action.disabled"
          :data-tooltip="action.tooltip"
          @click="action.onClick"
        >
          <i :class="['bi', action.icon]"></i>
        </button>
      </template>
    </div>

    <!-- 中間：頁面標題 -->
    <span v-if="pageTitle" class="app-title">{{ pageTitle }}</span>

    <!-- 右側：視窗控制 -->
    <div class="titlebar-right">
      <div class="window-controls">
        <button class="window-btn" @click="minimize" :title="$t('titlebar.minimize')">
          <IconMinimize />
        </button>
        <button class="window-btn" @click="toggleFullScreen" :title="isMaximized ? $t('titlebar.restore') : $t('titlebar.maximize')">
          <IconMaximize v-if="!isMaximized" />
          <IconRestore v-else />
        </button>
        <button class="window-btn close" @click="close" :title="$t('titlebar.close')">
          <IconClose />
        </button>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.titlebar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: transparent;
  z-index: 1000;
  user-select: none;
  -webkit-user-select: none;
  -webkit-app-region: drag;
}

.titlebar-left {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 138px; // 與右側 window-controls 寬度平衡（46px * 3）
  padding-left: 12px;
  -webkit-app-region: no-drag;
}

.titlebar-action {
  position: relative;
  width: 32px;
  height: 28px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
  font-size: 0.85rem;

  &:hover:not(:disabled) {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
  }

  &:active:not(:disabled) {
    background: var(--panel-bg-active);
  }

  &:disabled {
    opacity: 0.25;
    cursor: default;
  }

  &.is-highlighted {
    color: var(--color-primary);
  }

  // Tooltip — 下方浮出
  &::after {
    content: attr(data-tooltip);
    position: absolute;
    top: calc(100% + 4px);
    left: 50%;
    transform: translateX(-50%);
    padding: 4px 10px;
    background: var(--panel-bg-active);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid var(--panel-border);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 0.75rem;
    white-space: nowrap;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s ease;
    z-index: 100;
  }

  &:hover:not(:disabled)::after { opacity: 1; }

  &.is-active {
    background: var(--color-primary);
    color: #fff;
    opacity: 1;

    &:hover { background: var(--color-primary-hover); }
  }

  .flip-v {
    transform: scaleY(-1);
  }
}

.titlebar-separator {
  width: 1px;
  height: 16px;
  background: var(--panel-border);
  margin: 0 4px;
  opacity: 0.5;
}

.app-icon {
  width: 15px;
  height: 15px;
  border-radius: 3px;
  opacity: 0.6;
}

.titlebar-right {
  display: flex;
  align-items: center;
  -webkit-app-region: no-drag;
}

.app-title {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 500;
  pointer-events: none;
  max-width: 60%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.window-controls {
  display: flex;
}

.window-btn {
  width: 46px;
  height: 40px;
  padding: 0;
  border: 0;
  background-color: transparent;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  justify-content: center;

  svg {
    width: 18px;
    height: 18px;
  }

  &:hover {
    background-color: var(--panel-bg-hover);
  }

  &:active {
    background-color: var(--panel-bg-active);
  }

  &.close {
    &:hover {
      background-color: #e81123;
      color: white;
    }
    &:active {
      background-color: #f1707a;
    }
  }
}
</style>
