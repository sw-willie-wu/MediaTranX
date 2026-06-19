<script setup lang="ts">
import { ref, watch, useId } from 'vue'

const props = defineProps<{
  storageKey: string
  title?: string
}>()

const open = ref(localStorage.getItem(props.storageKey) === 'true')
watch(open, (v) => localStorage.setItem(props.storageKey, String(v)))

const bodyId = useId()
</script>

<template>
  <div class="settings-collapsible" :class="{ 'is-open': open }">
    <button
      class="settings-collapsible-header"
      type="button"
      :aria-expanded="open"
      :aria-controls="bodyId"
      @click="open = !open"
    >
      <i class="bi" :class="open ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
      <span>{{ title || $t('common.advanced_options') }}</span>
    </button>
    <div v-if="open" :id="bodyId" class="settings-collapsible-body">
      <slot />
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>
