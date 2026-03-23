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
const { activeFileName } = useTitlebar()

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
    <div class="titlebar-left"></div>

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
  min-width: 138px; // 與右側 window-controls 寬度平衡（46px * 3）
  padding-left: 12px;
  -webkit-app-region: no-drag;
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
