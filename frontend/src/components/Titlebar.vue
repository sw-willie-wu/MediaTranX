<script setup lang="ts">
import IconMinimize from './icons/IconMinimize.vue'
import IconMaximize from './icons/IconMaximize.vue'
import IconRestore from './icons/IconRestore.vue'
import IconClose from './icons/IconClose.vue'
import TitlebarButton from './common/TitlebarButton.vue'
import TitlebarResultsButton from './TitlebarResultsButton.vue'
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
  '/image': 'nav.image',
  '/video': 'nav.video',
  '/audio': 'nav.audio',
  '/document': 'nav.document',
}

// 非工具頁路徑
const pageTitleKeys: Record<string, string> = {
  '/tasks': 'nav.tasks',
  '/settings': 'nav.settings',
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
        <TitlebarButton
          icon="bi-arrow-return-left flip-v"
          :disabled="!canUndo"
          :tooltip="$t('titlebar.undo')"
          @click="undo"
        />
        <TitlebarButton
          icon="bi-arrow-return-right flip-v"
          :disabled="!canRedo"
          :tooltip="$t('titlebar.redo')"
          @click="redo"
        />
        <div v-if="extraActions.length" class="titlebar-separator"></div>
        <TitlebarButton
          v-for="action in extraActions"
          :key="action.id"
          :icon="action.icon"
          :active="action.active"
          :disabled="action.disabled"
          :tooltip="action.tooltip"
          @click="action.onClick"
        />
      </template>
    </div>

    <!-- 中間：頁面標題 + 當前檔案的另存 -->
    <div v-if="pageTitle" class="app-title-wrap">
      <span class="app-title">{{ pageTitle }}</span>
      <TitlebarButton
        v-if="isToolPage && canSaveAs"
        class="title-save"
        icon="bi-floppy"
        :tooltip="$t('titlebar.save_as')"
        @click="saveAs"
      />
    </div>

    <!-- 右側：視窗控制 -->
    <div class="titlebar-right">
      <TitlebarResultsButton />
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

// Button styling moved to common/TitlebarButton.vue (shared with results button).

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

.app-title-wrap {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 0.4rem;
  max-width: 60%;
}
.app-title {
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 500;
  pointer-events: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.title-save {
  -webkit-app-region: no-drag;
  flex-shrink: 0;
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
