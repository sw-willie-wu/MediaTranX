<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import TabbedLayout from '@/components/common/TabbedLayout.vue'
import SettingsGeneral from '@/components/settings/SettingsGeneral.vue'
import SettingsSystem from '@/components/settings/SettingsSystem.vue'
import SettingsModels from '@/components/settings/SettingsModels.vue'
import SettingsAbout from '@/components/settings/SettingsAbout.vue'
import SettingsAgent from '@/components/settings/SettingsAgent.vue'
import SettingsVideoDownload from '@/components/settings/SettingsVideoDownload.vue'
import { useViewHost } from '@/composables/useViewHost'
import { subfunctionsForView } from '@/agent/agentNavCatalog'

const { t } = useI18n()
const route = useRoute()

const activeTab = ref((route.query.tab as string) || 'general')

// Deep-link support when ALREADY on /settings: the initial ref only reads the
// query once at mount, so a later push({ query: { tab } }) (e.g. the no-model
// assistant redirect) wouldn't switch the tab without this. Guarded so an
// undefined/removed tab query is a no-op (doesn't fight tab clicks, which don't
// touch the route).
watch(() => route.query.tab, (tab) => {
  if (tab) activeTab.value = tab as string
})

useViewHost('settings', {
  currentFunction: activeTab,
  setCurrentFunction: (id) => { activeTab.value = id },
  validSubfunctions: () => subfunctionsForView('settings'),
})

const tabs = computed(() => [
  { id: 'general', icon: 'bi-sliders',      label: t('settings.tab.general') },
  { id: 'system',  icon: 'bi-cpu',          label: t('settings.tab.system') },
  { id: 'models',  icon: 'bi-boxes',        label: t('settings.tab.models') },
  { id: 'agent',          icon: 'bi-robot',        label: t('settings.tab.agent') },
  { id: 'video-download', icon: 'bi-download',     label: t('settings.tab.video-download') },
  { id: 'about',          icon: 'bi-info-circle',  label: t('settings.tab.about') },
])
</script>

<template>
  <TabbedLayout v-model="activeTab" :tabs="tabs">
    <SettingsGeneral v-if="activeTab === 'general'" />
    <SettingsSystem  v-else-if="activeTab === 'system'" />
    <SettingsModels  v-else-if="activeTab === 'models'" />
    <SettingsAgent         v-else-if="activeTab === 'agent'" />
    <SettingsVideoDownload v-else-if="activeTab === 'video-download'" />
    <SettingsAbout         v-else-if="activeTab === 'about'" />
  </TabbedLayout>
</template>
