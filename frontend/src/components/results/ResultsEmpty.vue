<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
</script>

<template>
  <div class="results-empty">
    <i class="bi bi-inbox"></i>
    <p>{{ t('results.empty') }}</p>
  </div>
</template>

<style lang="scss" scoped>
.results-empty {
  padding: 2.5rem 1rem;
  text-align: center;
  color: var(--text-muted);

  i { font-size: 2.5rem; opacity: 0.5; display: block; margin-bottom: 0.5rem; }
  p { font-size: 0.85rem; margin: 0; }
}
</style>
