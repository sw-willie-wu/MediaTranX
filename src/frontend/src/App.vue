<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'
import Titlebar from './components/Titlebar.vue'
import MainSidebar from './components/MainSidebar.vue'
import AppToast from './components/AppToast.vue'
import { useTheme } from './composables/useTheme'

// 初始化主題
useTheme()

// Vue 掛載後淡出 splash overlay
onMounted(() => {
  const overlay = document.getElementById('splash-overlay')
  if (overlay) {
    overlay.classList.add('fade-out')
    setTimeout(() => overlay.remove(), 300)
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
