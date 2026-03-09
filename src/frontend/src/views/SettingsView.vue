<script setup lang="ts">
import { ref } from 'vue'
import SettingsGeneral from '@/components/settings/SettingsGeneral.vue'
import SettingsSystem from '@/components/settings/SettingsSystem.vue'
import SettingsModels from '@/components/settings/SettingsModels.vue'
import SettingsAbout from '@/components/settings/SettingsAbout.vue'

type SectionId = 'general' | 'system' | 'models' | 'about'

const activeSection = ref<SectionId>('general')

const sections: { id: SectionId; icon: string; label: string }[] = [
  { id: 'general', icon: 'bi-sliders',      label: '一般' },
  { id: 'system',  icon: 'bi-cpu',          label: '系統資訊' },
  { id: 'models',  icon: 'bi-boxes',        label: 'AI 模組管理' },
  { id: 'about',   icon: 'bi-info-circle',  label: '關於' },
]
</script>

<template>
  <div class="settings-layout">
    <!-- 左側 sidebar -->
    <aside class="settings-sidebar">
      <div class="sidebar-list">
        <button
          v-for="s in sections"
          :key="s.id"
          class="sidebar-item"
          :class="{ active: activeSection === s.id }"
          @click="activeSection = s.id"
        >
          <i :class="['bi', s.icon]"></i>
          <span>{{ s.label }}</span>
        </button>
      </div>
    </aside>

    <!-- 右側 content -->
    <main class="settings-content">
      <div class="section-content">
        <SettingsGeneral v-if="activeSection === 'general'" />
        <SettingsSystem  v-else-if="activeSection === 'system'" />
        <SettingsModels  v-else-if="activeSection === 'models'" />
        <SettingsAbout   v-else-if="activeSection === 'about'" />
      </div>
    </main>
  </div>
</template>

<style lang="scss" scoped>
.settings-layout {
  display: flex;
  height: calc(100vh - 40px);
  gap: 1rem;
  padding: 1rem;
}

.settings-sidebar {
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

.sidebar-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.sidebar-item {
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

  i    { font-size: 1.1rem; width: 22px; }
  span { font-size: 0.9rem; }

  &:hover, &.active {
    color: var(--text-primary);
    background: var(--panel-bg);
  }
}

.settings-content {
  flex: 1;
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  padding: 1.5rem;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.section-content {
  max-width: 560px;
  margin: 0 auto;
}
</style>
