<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import TabbedLayout from '@/components/common/TabbedLayout.vue'
import SettingsGeneral from '@/components/settings/SettingsGeneral.vue'
import SettingsSystem from '@/components/settings/SettingsSystem.vue'
import SettingsModels from '@/components/settings/SettingsModels.vue'
import SettingsAbout from '@/components/settings/SettingsAbout.vue'
import SettingsAgent from '@/components/settings/SettingsAgent.vue'
import { useViewHost } from '@/composables/useViewHost'

const { t } = useI18n()
const route = useRoute()

const activeTab = ref((route.query.tab as string) || 'general')

useViewHost('settings', {
  currentFunction: activeTab,
  setCurrentFunction: (id) => { activeTab.value = id },
  validSubfunctions: () => ['general', 'system', 'models', 'agent', 'about'],
})

const tabs = computed(() => [
  { id: 'general', icon: 'bi-sliders',      label: t('settings.tab.general') },
  { id: 'system',  icon: 'bi-cpu',          label: t('settings.tab.system') },
  { id: 'models',  icon: 'bi-boxes',        label: t('settings.tab.models') },
  { id: 'agent',   icon: 'bi-robot',        label: t('settings.tab.agent') },
  { id: 'about',   icon: 'bi-info-circle',  label: t('settings.tab.about') },
])
</script>

<template>
  <TabbedLayout v-model="activeTab" :tabs="tabs">
    <SettingsGeneral v-if="activeTab === 'general'" />
    <SettingsSystem  v-else-if="activeTab === 'system'" />
    <SettingsModels  v-else-if="activeTab === 'models'" />
    <SettingsAgent   v-else-if="activeTab === 'agent'" />
    <SettingsAbout   v-else-if="activeTab === 'about'" />
  </TabbedLayout>
</template>
