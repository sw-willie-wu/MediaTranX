<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/tasks'
import TabbedLayout from '@/components/common/TabbedLayout.vue'
import TasksActive from '@/components/tasks/TasksActive.vue'
import TasksHistory from '@/components/tasks/TasksHistory.vue'

const { t } = useI18n()
const route = useRoute()
const taskStore = useTaskStore()

const activeTab = ref(route.query.tab === 'history' ? 'history' : 'active')

const tabs = computed(() => [
  { id: 'active',  icon: 'bi-list-task',    label: t('tasks.active.title'), badge: taskStore.activeCount },
  { id: 'history', icon: 'bi-clock-history', label: t('tasks.history.title') },
])
</script>

<template>
  <TabbedLayout v-model="activeTab" :tabs="tabs" content-max-width="560px">
    <TasksActive  v-if="activeTab === 'active'" />
    <TasksHistory v-else-if="activeTab === 'history'" />
  </TabbedLayout>
</template>
