<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterView } from 'vue-router'
import Titlebar from './components/Titlebar.vue'
import MainSidebar from './components/MainSidebar.vue'
import AppToast from './components/AppToast.vue'
import AppSetupWizard from './components/common/AppSetupWizard.vue'
import { useTheme } from './composables/useTheme'

// 初始化主題
useTheme()

const showWizard = ref(false)
const AI_CACHE_KEY = 'ai-module-cache'

function removeSplash() {
  const overlay = document.getElementById('splash-overlay')
  if (overlay) {
    overlay.classList.add('fade-out')
    setTimeout(() => overlay.remove(), 300)
  }
}

function isWizardEnabled(): boolean {
  try {
    const saved = localStorage.getItem('app-settings')
    return saved ? (JSON.parse(saved).showSetupWizard ?? true) : true
  } catch { return true }
}

function readAiCache(): { aiEnvReady: boolean; llamaReady: boolean } | null {
  try {
    const s = localStorage.getItem(AI_CACHE_KEY)
    return s ? JSON.parse(s) : null
  } catch { return null }
}

async function fetchAndCacheStatus(): Promise<boolean> {
  try {
    const res = await fetch('/api/setup/status')
    const data = await res.json()
    const notReady = !data.ai_env_ready || !(data.llama_ready ?? false)
    localStorage.setItem(AI_CACHE_KEY, JSON.stringify({
      aiEnvReady: data.ai_env_ready,
      llamaReady: data.llama_ready ?? false,
      torchIndex: data.torch_index ?? 'cpu',
      driverVersion: data.device?.driver_version ?? null,
    }))
    return notReady
  } catch {
    return false
  }
}

// Vue 掛載後處理 splash 與 wizard 邏輯
onMounted(async () => {
  if (!isWizardEnabled()) {
    removeSplash()
    // 背景更新快取
    fetchAndCacheStatus()
    return
  }

  const cache = readAiCache()
  if (cache) {
    // 有快取：同步決定，立刻移除 splash
    showWizard.value = !cache.aiEnvReady || !cache.llamaReady
    removeSplash()
    // 背景更新快取；若狀態改變（例如用戶手動刪 .venv）則補顯示 wizard
    fetchAndCacheStatus().then((notReady) => {
      if (notReady) showWizard.value = true
    })
  } else {
    // 第一次啟動：等後端回應才移除 splash
    const notReady = await fetchAndCacheStatus()
    showWizard.value = notReady
    removeSplash()
  }
})
</script>

<template>
  <div class="app-wrapper app-enter">
    <Titlebar />
    <MainSidebar />
    <div class="app-content">
      <RouterView v-slot="{ Component }">
        <KeepAlive>
          <component :is="Component" />
        </KeepAlive>
      </RouterView>
    </div>
    <AppToast />
    <AppSetupWizard v-if="showWizard" @close="showWizard = false" />
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
