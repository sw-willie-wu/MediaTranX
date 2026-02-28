<script setup lang="ts">
export interface InfoItem {
  icon: string
  label: string
}

defineProps<{
  items?: InfoItem[]
  loading?: boolean
  loadingText?: string
}>()
</script>

<template>
  <div class="media-info-bar" :class="{ loading }">
    <template v-if="loading">
      <div class="spinner-border spinner-border-sm" role="status"></div>
      <span>{{ loadingText ?? '讀取資訊...' }}</span>
    </template>
    <template v-else-if="items?.length">
      <div v-for="(item, i) in items" :key="i" class="info-item">
        <i :class="['bi', item.icon]"></i>
        <span>{{ item.label }}</span>
      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.media-info-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem 1rem;
  padding: 0.6rem 1rem;
  border-top: 1px solid var(--panel-border);
  flex-shrink: 0;

  &.loading {
    gap: 0.5rem;
    color: var(--text-muted);
    font-size: 0.85rem;
  }
}

.info-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.8rem;
  color: var(--text-secondary);

  i {
    font-size: 0.7rem;
    color: var(--text-muted);
  }
}
</style>
