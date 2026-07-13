<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

export interface InfoItem {
  icon: string
  label: string
  /** 給了就渲染成可點擊項（如縮放百分比→點擊重置/fit）；title 為 hover 提示 */
  onClick?: () => void
  title?: string
}

withDefaults(defineProps<{
  items?: InfoItem[]
  loading?: boolean
  loadingText?: string
  overlay?: boolean
}>(), {
  overlay: false,
})
</script>

<template>
  <div class="media-info-bar" :class="{ loading, 'is-overlay': overlay }">
    <template v-if="loading">
      <div class="spinner-border spinner-border-sm" role="status"></div>
      <span>{{ loadingText ?? t('common.loading_info') }}</span>
    </template>
    <template v-else-if="items?.length">
      <component
        :is="item.onClick ? 'button' : 'div'"
        v-for="(item, i) in items"
        :key="i"
        class="info-item"
        :class="{ 'is-clickable': !!item.onClick }"
        :title="item.title"
        @click="item.onClick?.()"
      >
        <i :class="['bi', item.icon]"></i>
        <span>{{ item.label }}</span>
      </component>
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

  &.is-overlay {
    border-top: none;
    padding: 0.35rem 0.65rem;
    gap: 0.3rem 0.8rem;
    background: transparent;
    justify-content: center;
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

  &.is-clickable {
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    transition: color 0.15s ease;

    &:hover {
      color: var(--color-primary);
      i { color: var(--color-primary); }
    }
  }
}
</style>
