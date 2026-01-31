<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterView } from 'vue-router'
import Titlebar from './components/Titlebar.vue'
import MainSidebar from './components/MainSidebar.vue'
import { useTheme } from './composables/useTheme'

// 初始化主題
useTheme()

// 後端就緒狀態
const backendReady = ref(false)
const splashFading = ref(false)

// 輪詢後端健康檢查
onMounted(async () => {
  const maxAttempts = 120
  let attempts = 0

  while (attempts < maxAttempts) {
    try {
      const res = await fetch('/api/health')
      if (res.ok) {
        // 後端就緒，開始淡出動畫
        splashFading.value = true
        setTimeout(() => {
          backendReady.value = true
        }, 500)
        return
      }
    } catch {
      // 後端尚未就緒
    }
    attempts++
    await new Promise(r => setTimeout(r, 500))
  }

  // 超過最大嘗試次數，仍然顯示主畫面
  backendReady.value = true
})
</script>

<template>
  <!-- 啟動畫面 -->
  <div v-if="!backendReady" class="splash-screen" :class="{ 'fade-out': splashFading }">
    <Titlebar />
    <div class="splash-content">
      <div class="splash-logo">
        <img src="@/assets/icon.svg" alt="MediaTranX" class="splash-icon" />
      </div>
      <h1 class="splash-title">MediaTranX</h1>
      <div class="splash-loader">
        <div class="splash-loader-bar"></div>
      </div>
      <p class="splash-hint">正在初始化...</p>
    </div>
  </div>

  <!-- 主畫面 -->
  <div v-else class="app-wrapper app-enter">
    <Titlebar />
    <MainSidebar />
    <div class="app-content">
      <RouterView />
    </div>
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

// 啟動畫面
.splash-screen {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  transition: opacity 0.5s ease;

  &.fade-out {
    opacity: 0;
  }
}

.splash-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding-bottom: 80px;
}

.splash-logo {
  margin-bottom: 1.5rem;
}

.splash-icon {
  width: 88px;
  height: 88px;
  border-radius: 20px;
}

.splash-title {
  font-size: 1.6rem;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.05em;
  margin-bottom: 2rem;
}

.splash-loader {
  width: 180px;
  height: 3px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 1.2rem;
}

.splash-loader-bar {
  width: 40%;
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary), var(--color-accent));
  border-radius: 2px;
  animation: loaderSlide 1.5s ease-in-out infinite;
}

@keyframes loaderSlide {
  0% { transform: translateX(-100%); }
  50% { transform: translateX(200%); }
  100% { transform: translateX(-100%); }
}

.splash-hint {
  font-size: 0.85rem;
  color: var(--text-muted);
}
</style>
