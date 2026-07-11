<script setup lang="ts">
/**
 * 通用三欄殼 — 擁有三欄 panel chrome、resize handle 與寬度（全 app 共用
 * useResizableLayout singleton）。內容 padding / 捲動 / 行為屬 slot 使用方。
 * 覆寫欄 chrome 樣式須寫 :deep(.tp-<pane>.<class>) — 見 spec 2026-07-07。
 */
import { useResizableLayout, DEFAULTS } from '@/composables/useResizableLayout'

defineProps<{
  leftClass?: string | Record<string, boolean>
  centerClass?: string | Record<string, boolean>
  rightClass?: string | Record<string, boolean>
}>()

const { sidebarWidth, settingsWidth, startResize } = useResizableLayout()
</script>

<template>
  <div class="three-pane-layout">
    <aside class="tp-left" :class="leftClass" :style="{ width: sidebarWidth + 'px', minWidth: sidebarWidth + 'px' }">
      <slot name="left" />
    </aside>

    <div class="resize-handle" @mousedown="startResize('sidebar', $event)" @dblclick="sidebarWidth = DEFAULTS.sidebar"></div>

    <main class="tp-center" :class="centerClass">
      <slot name="center" />
    </main>

    <div class="resize-handle" @mousedown="startResize('settings', $event)" @dblclick="settingsWidth = DEFAULTS.settings"></div>

    <aside class="tp-right" :class="rightClass" :style="{ width: settingsWidth + 'px', minWidth: settingsWidth + 'px' }">
      <slot name="right" />
    </aside>
  </div>
</template>

<style lang="scss">
@use '@/styles/layout-shared';
</style>

<style lang="scss" scoped>
.three-pane-layout {
  display: flex;
  height: calc(100vh - 40px);
  gap: 0;
  padding: 0.5rem 1rem 1rem 0;
}

%pane-chrome {
  background: var(--panel-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
}

.tp-left {
  @extend %pane-chrome;
  position: relative;
  display: flex;
  flex-direction: column;
}

.tp-center {
  @extend %pane-chrome;
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tp-right {
  @extend %pane-chrome;
  display: flex;
  flex-direction: column;
}
</style>
