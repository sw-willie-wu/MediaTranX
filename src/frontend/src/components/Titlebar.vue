<script setup lang="ts">
import IconMinimize from './icons/IconMinimize.vue'
import IconMaximize from './icons/IconMaximize.vue'
import IconRestore from './icons/IconRestore.vue'
import IconClose from './icons/IconClose.vue'
import SettingsModal from './SettingsModal.vue'
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const isMaximized = ref(false)
const showSettings = ref(false)

// 頁面標題對應
const pageTitles: Record<string, string> = {
  '/': '',
  '/image': '圖片工具',
  '/video': '影片工具',
  '/audio': '音訊工具',
  '/document': '文件工具',
  '/history': '歷史紀錄',
  '/tasks': '執行任務',
}

const pageTitle = computed(() => {
  const title = pageTitles[route.path]
  return title ? ` - ${title}` : ''
})

function openSettings() {
  showSettings.value = true
}

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
    <!-- 左側：App icon + 標題 -->
    <div class="titlebar-left">
      <img src="@/assets/icon.svg" alt="" class="app-icon" />
      <span class="app-title">MediaTranX{{ pageTitle }}</span>
    </div>

    <!-- 右側：設定 + 視窗控制 -->
    <div class="titlebar-right">
      <button
        class="titlebar-btn settings-btn"
        @click="openSettings"
        :class="{ active: showSettings }"
        title="設定"
      >
        <i class="bi bi-gear-fill"></i>
      </button>

      <!-- 設定 Modal -->
      <SettingsModal :show="showSettings" @close="showSettings = false" />

      <div class="window-controls">
        <button class="window-btn" @click="minimize" title="最小化">
          <IconMinimize />
        </button>
        <button class="window-btn" @click="toggleFullScreen" :title="isMaximized ? '還原' : '最大化'">
          <IconMaximize v-if="!isMaximized" />
          <IconRestore v-else />
        </button>
        <button class="window-btn close" @click="close" title="關閉">
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
  gap: 0.5rem;
  padding-left: 12px;
  -webkit-app-region: no-drag;
}

.titlebar-right {
  display: flex;
  align-items: center;
  -webkit-app-region: no-drag;
}

.app-title {
  color: var(--text-primary);
  font-size: 0.9rem;
  font-weight: 500;
  padding-left: 0.5rem;
  -webkit-app-region: drag;
}

.app-icon {
  width: 18px;
  height: 18px;
  border-radius: 4px;
}

.titlebar-btn {
  width: 36px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;

  i {
    font-size: 1rem;
  }

  &:hover {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
  }

  &:active {
    background: var(--panel-bg-active);
  }

  &.active {
    color: var(--color-accent);
  }
}

.settings-btn {
  margin-right: 1rem;
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
