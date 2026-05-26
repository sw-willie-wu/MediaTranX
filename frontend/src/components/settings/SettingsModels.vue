<script setup lang="ts">
import ModelDownloadManager from '@/components/settings/ModelDownloadManager.vue'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

useAgentPanelHost('settings.models', {
  agentSchema: {
    panelId: 'settings.models',
    fields: [],
    actions: [
      { name: 'download_model', label: 'Download Model' },
    ],
    execute: null,
  },
  getCurrentValues: () => ({}),
  setField: (_field: string, _value: unknown) => {
    throw new Error('agent.error.no_execute_on_settings')
  },
  openField: (_field: string) => {},
  execute: () => { throw new Error('agent.error.no_execute_on_settings') },
  invokeAction: (_name: string) => { /* Model download is handled by ModelDownloadManager UI */ },
  isMultiSelect: () => false,
})
</script>

<template>
  <ModelDownloadManager />
</template>
