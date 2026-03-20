<script setup lang="ts">
import { ref } from 'vue'
import TabbedLayout from '@/components/common/TabbedLayout.vue'
import type { TabItem } from '@/components/common/TabbedLayout.vue'
import SettingsGeneral from '@/components/settings/SettingsGeneral.vue'
import SettingsSystem from '@/components/settings/SettingsSystem.vue'
import SettingsModels from '@/components/settings/SettingsModels.vue'
import SettingsAbout from '@/components/settings/SettingsAbout.vue'

const activeTab = ref('general')

const tabs: TabItem[] = [
  { id: 'general', icon: 'bi-sliders',      label: '一般' },
  { id: 'system',  icon: 'bi-cpu',          label: '系統資訊' },
  { id: 'models',  icon: 'bi-boxes',        label: 'AI 模組管理' },
  { id: 'about',   icon: 'bi-info-circle',  label: '關於' },
]
</script>

<template>
  <TabbedLayout v-model="activeTab" :tabs="tabs">
    <SettingsGeneral v-if="activeTab === 'general'" />
    <SettingsSystem  v-else-if="activeTab === 'system'" />
    <SettingsModels  v-else-if="activeTab === 'models'" />
    <SettingsAbout   v-else-if="activeTab === 'about'" />
  </TabbedLayout>
</template>
