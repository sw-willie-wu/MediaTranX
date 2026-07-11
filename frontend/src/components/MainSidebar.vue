<script setup lang="ts">
import { ref, watch, onMounted, nextTick, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/tasks'
import { isPipelineEnabled } from '@/utils/featureGate'

const route = useRoute()
const router = useRouter()
const taskStore = useTaskStore()
const { t } = useI18n()

interface NavItem {
  path: string
  icon: string
  labelKey: string
}

const topNavDef: NavItem[] = [
  { path: '/', icon: 'bi-house-fill', labelKey: 'nav.home' },
  { path: '/image', icon: 'bi-image-fill', labelKey: 'nav.image' },
  { path: '/audio', icon: 'bi-music-note-beamed', labelKey: 'nav.audio' },
  { path: '/video', icon: 'bi-film', labelKey: 'nav.video' },
  { path: '/document', icon: 'bi-file-earmark-text-fill', labelKey: 'nav.document' },
  { path: '/pipeline', icon: 'bi-diagram-3-fill', labelKey: 'nav.pipeline' },
]

const bottomNavDef: NavItem[] = [
  { path: '/tasks', icon: 'bi-list-task', labelKey: 'nav.tasks' },
  { path: '/settings', icon: 'bi-gear-fill', labelKey: 'nav.settings' },
]

// stable channel 隱藏流程入口（spec: pipeline-feature-gate §3.3）
const visibleTopNavDef = topNavDef.filter(i => i.path !== '/pipeline' || isPipelineEnabled())

const topNav = computed(() => visibleTopNavDef.map(item => ({ ...item, label: t(item.labelKey) })))
const bottomNav = computed(() => bottomNavDef.map(item => ({ ...item, label: t(item.labelKey) })))

// 指示條位置
const buttonRefs = ref<Record<string, HTMLElement | null>>({})
const indicatorTop = ref(0)
const indicatorVisible = ref(false)

function updateIndicator() {
  const path = route.path
  const el = buttonRefs.value[path]
  if (el) {
    indicatorTop.value = el.offsetTop + (el.offsetHeight - 20) / 2
    indicatorVisible.value = true
  }
}

function setButtonRef(path: string, el: HTMLElement | null) {
  buttonRefs.value[path] = el
}

watch(() => route.path, () => {
  nextTick(updateIndicator)
})

onMounted(() => {
  nextTick(updateIndicator)
})

function isActive(path: string) {
  return route.path === path
}

function navigate(path: string) {
  router.push(path)
}

function restartApp() {
  if (window.electron?.restart) {
    window.electron.restart()
  } else {
    window.location.reload()
  }
}
</script>

<template>
  <nav class="main-sidebar">
    <!-- 動畫指示條 -->
    <div
      class="indicator"
      :style="{
        top: `${indicatorTop}px`,
        opacity: indicatorVisible ? 1 : 0
      }"
    ></div>
    <div class="nav-top">
      <button
        v-for="item in topNav"
        :key="item.path"
        :ref="(el) => setButtonRef(item.path, el as HTMLElement)"
        class="nav-btn"
        :class="{ 'is-active': isActive(item.path) }"
        :data-tooltip="item.label"
        @click="navigate(item.path)"
      >
        <i class="bi" :class="item.icon"></i>
      </button>
    </div>
    <div class="nav-bottom">
      <button
        v-for="item in bottomNav"
        :key="item.path"
        :ref="(el) => setButtonRef(item.path, el as HTMLElement)"
        class="nav-btn"
        :class="{ 'is-active': isActive(item.path) }"
        :data-tooltip="item.label"
        @click="navigate(item.path)"
      >
        <i class="bi" :class="item.icon"></i>
        <span
          v-if="item.path === '/tasks' && taskStore.activeCount > 0"
          class="nav-badge"
        >{{ taskStore.activeCount }}</span>
      </button>
      <button
        class="nav-btn restart-btn"
        :data-tooltip="$t('nav.restart')"
        @click="restartApp"
      >
        <i class="bi bi-arrow-clockwise"></i>
      </button>
    </div>
  </nav>
</template>

<style lang="scss" scoped>
.main-sidebar {
  position: fixed;
  top: 40px;
  left: 0;
  bottom: 0;
  width: var(--main-sidebar-width, 52px);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 0;
  background: transparent;
  z-index: 900;
}

.indicator {
  position: absolute;
  left: 10px;
  width: 3px;
  height: 20px;
  background: var(--color-accent);
  border-radius: 0 2px 2px 0;
  transition: top 0.15s ease-in-out, opacity 0.15s ease;
  z-index: 1;
}

.nav-top {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.nav-bottom {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding-bottom: 4px;
}

.nav-btn {
  position: relative;
  width: 40px;
  height: 40px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;

  i {
    font-size: 1.1rem;
  }

  &:hover {
    background: var(--panel-bg-hover);
    color: var(--text-primary);
  }

  &:active {
    background: var(--panel-bg-active);
  }

  &.is-active {
    color: var(--text-primary);
  }

  // CSS tooltip - 右側浮出
  &::after {
    content: attr(data-tooltip);
    position: absolute;
    left: calc(100% + 8px);
    top: 50%;
    transform: translateY(-50%);
    padding: 4px 10px;
    background: var(--panel-bg-active);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid var(--panel-border);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 0.8rem;
    white-space: nowrap;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s ease;
    z-index: 1000;
  }

  &:hover::after {
    opacity: 1;
  }
}

.nav-badge {
  position: absolute;
  top: 4px;
  right: 2px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  background: var(--color-accent);
  color: var(--text-primary);
  font-size: 0.6rem;
  font-weight: 600;
  line-height: 16px;
  text-align: center;
  border-radius: 8px;
  pointer-events: none;
}
</style>
