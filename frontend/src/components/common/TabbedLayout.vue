<script lang="ts">
export interface TabItem {
  id: string
  icon: string
  label: string
  badge?: number
}
</script>

<script setup lang="ts">
import { computed } from 'vue'
import { useResizableLayout } from '@/composables/useResizableLayout'

const { sidebarWidth, startResize } = useResizableLayout()

const props = withDefaults(defineProps<{
  tabs: TabItem[]
  modelValue: string
  contentMaxWidth?: string
}>(), {
  contentMaxWidth: '560px',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const activeTab = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})
</script>

<template>
  <div class="tabbed-layout">
    <aside class="tabbed-sidebar" :style="{ width: sidebarWidth + 'px', minWidth: sidebarWidth + 'px' }">
      <div class="sidebar-list">
        <button
          v-for="t in tabs"
          :key="t.id"
          class="sidebar-item"
          :class="{ 'is-active': activeTab === t.id }"
          @click="activeTab = t.id"
        >
          <i :class="['bi', t.icon]"></i>
          <span>{{ t.label }}</span>
          <span v-if="t.badge && t.badge > 0" class="sidebar-badge">{{ t.badge }}</span>
        </button>
      </div>
    </aside>

    <div class="resize-handle" @mousedown="startResize('sidebar', $event)" @dblclick="sidebarWidth = 180"></div>

    <main class="tabbed-content">
      <div class="content-inner" :style="{ maxWidth: contentMaxWidth }">
        <slot />
      </div>
    </main>
  </div>
</template>

<style lang="scss">
@use '@/styles/layout-shared';
</style>

<style lang="scss" scoped>
.tabbed-layout {
  display: flex;
  height: calc(100vh - 40px);
  gap: 0;
  padding: 1rem;
}

.tabbed-sidebar {
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

  &:hover {
    color: var(--text-primary);
    background: var(--panel-bg-hover);
  }

  &.is-active {
    color: var(--text-primary);
    background: var(--panel-bg-active);

    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 20%;
      bottom: 20%;
      width: 3px;
      border-radius: 0 2px 2px 0;
      background: var(--color-accent);
    }
  }
}

.sidebar-badge {
  margin-left: auto;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: var(--color-accent);
  color: var(--text-primary);
  font-size: 0.6rem !important;
  font-weight: 600;
  line-height: 18px;
  text-align: center;
  border-radius: 9px;
}

.tabbed-content {
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

.content-inner {
  margin: 0 auto;
}
</style>
