<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter, RouterView } from 'vue-router'
import Titlebar from './components/Titlebar.vue'
import MainSidebar from './components/MainSidebar.vue'
import AppToast from './components/AppToast.vue'
import AppConfirmDialog from './components/common/AppConfirmDialog.vue'
import AgentRunBanner from './components/agent/AgentRunBanner.vue'
import ChatBubble from './components/agent/ChatBubble.vue'
import { useTheme } from './composables/useTheme'
import { useRemoteModelStore } from './stores/remoteModels'
import { useResultsStore } from './stores/results'
import { useAgentStore } from './stores/agent'

const router = useRouter()

// 初始化主題
useTheme()

// 啟動時背景 fetch 雲端模型
const remoteModelStore = useRemoteModelStore()
remoteModelStore.fetchAll()

// Results drawer store
const resultsStore = useResultsStore()

// Agent store (for banner visibility)
const agentStore = useAgentStore()

function removeSplash() {
  const overlay = document.getElementById('splash-overlay')
  if (overlay) {
    overlay.classList.add('fade-out')
    setTimeout(() => overlay.remove(), 300)
  }
}

// Vue 掛載後處理 splash
onMounted(async () => {
  await router.isReady()

  if (router.currentRoute.value.path === '/' && !window.location.hash) {
    router.replace('/')
  }

  // 啟動 Results drawer：先掛 watcher（避免錯過早期完成的任務），再載入既有 output 檔
  resultsStore.startAutoCollect()
  await resultsStore.loadInitial()

  removeSplash()
})
</script>

<template>
  <div class="app-wrapper app-enter">
    <Titlebar />
    <AgentRunBanner v-if="agentStore.isRunning" />
    <MainSidebar />
    <div class="app-content" :class="{ 'is-agent-running': agentStore.isRunning }">
      <RouterView v-slot="{ Component }">
        <KeepAlive>
          <component :is="Component" :key="$route.fullPath" />
        </KeepAlive>
      </RouterView>
    </div>
    <AppToast />
    <AppConfirmDialog />
    <ChatBubble />
  </div>
</template>

<style lang="scss">
.app-wrapper {
  --main-sidebar-width: 60px;
  min-height: 100vh;
}

.app-content {
  padding-top: 40px;
  margin-left: var(--main-sidebar-width);
  min-height: 100vh;

  &.is-agent-running {
    padding-top: 72px; /* 40px titlebar + 32px agent banner */
  }
}

// 全域樣式：玻璃面板
.glass-panel {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
}

// 主畫面淡入
.app-enter {
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

</style>
