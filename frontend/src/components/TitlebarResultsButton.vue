<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useResultsStore } from '@/stores/results'
import TitlebarButton from './common/TitlebarButton.vue'
import ResultsDropdown from './ResultsDropdown.vue'
import { prefetchToolViews } from '@/router/prefetchViews'

const { t } = useI18n()
const resultsStore = useResultsStore()
const open = ref(false)

const count = computed(() => resultsStore.results.length)
const unreadCount = computed(() => resultsStore.unreadCount)
const hasUnread = computed(() => unreadCount.value > 0)
const hasFiles = computed(() => count.value > 0)

function toggle() {
  open.value = !open.value
  if (open.value) {
    resultsStore.markRead()
    // 抽屜開啟＝即將 open-in-tool 的強意圖——預熱工具頁 chunk，讓之後 router.push 幾乎即時
    prefetchToolViews()
  }
}
function close() { open.value = false }
</script>

<template>
  <div class="results-button-wrap" :class="{ 'has-unread': hasUnread }">
    <TitlebarButton
      :icon="hasFiles ? 'bi-inbox-fill' : 'bi-inbox'"
      :tooltip="t('results.title')"
      :highlighted="hasFiles && !open"
      :active="open"
      @click="toggle"
    >
      <span v-if="hasUnread" class="badge">{{ unreadCount }}</span>
    </TitlebarButton>
    <Transition name="dropdown">
      <ResultsDropdown v-if="open" @close="close" />
    </Transition>
  </div>
</template>

<style lang="scss" scoped>
.results-button-wrap {
  position: relative;
  -webkit-app-region: no-drag;
  margin-right: 4px;
}
.badge {
  position: absolute;
  top: 2px;
  right: 0;
  min-width: 13px;
  height: 13px;
  padding: 0 3px;
  border-radius: 7px;
  background: var(--color-accent);
  color: var(--text-primary);
  font-size: 0.55rem;
  font-weight: 600;
  line-height: 13px;
  text-align: center;
  pointer-events: none;
}
.has-unread .badge {
  transform-origin: center;
  animation: badge-pulse 1.4s ease-in-out infinite;
}
@keyframes badge-pulse {
  0%, 100% {
    transform: scale(1);
    box-shadow: 0 0 0 0 rgba(168, 156, 200, 0.7);
  }
  50% {
    transform: scale(1.18);
    box-shadow: 0 0 0 6px rgba(168, 156, 200, 0);
  }
}
.dropdown-enter-active,
.dropdown-leave-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.dropdown-enter-from,
.dropdown-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
