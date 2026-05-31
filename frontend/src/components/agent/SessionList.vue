<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiFetch } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useAgent } from '@/composables/useAgent'
import { formatRelativeTime } from '@/utils/relativeTime'

interface SessionRow {
  id: string
  last_preview: string
  updated_at: string
  message_count: number
}

const emit = defineEmits<{
  (e: 'select', id: string): void
  (e: 'new-chat'): void
}>()

const { t } = useI18n()
const { show } = useToast()
const agent = useAgent()
const sessions = ref<SessionRow[]>([])

async function loadList() {
  try {
    const res = await apiFetch('/agent/sessions')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    sessions.value = await res.json()
  } catch (e) {
    console.warn('[SessionList] load failed:', e)
    show(t('agent.session.load_failed'), { type: 'error' })
  }
}

async function onDelete(id: string) {
  if (!window.confirm(t('agent.session.delete_confirm'))) return
  try {
    await agent.deleteSession(id)
    await loadList()
  } catch (e) {
    console.warn('[SessionList] delete failed:', e)
    show(t('agent.session.delete_failed'), { type: 'error' })
  }
}

onMounted(loadList)
</script>

<template>
  <div class="session-list">
    <button class="session-new-btn" @click="emit('new-chat')">
      <i class="bi bi-plus-lg"></i>
      {{ $t('agent.session.new_chat') }}
    </button>

    <div v-if="sessions.length === 0" class="session-empty">
      {{ $t('agent.session.empty') }}
    </div>

    <ul v-else class="session-rows">
      <li v-for="s in sessions" :key="s.id" class="session-row">
        <div class="session-row-main" @click="emit('select', s.id)">
          <span class="session-preview">{{ s.last_preview || $t('agent.bubble.empty') }}</span>
          <span class="session-time">{{ formatRelativeTime(s.updated_at, t) }}</span>
        </div>
        <button
          class="session-delete-btn"
          :title="$t('agent.session.delete')"
          :aria-label="$t('agent.session.delete')"
          @click.stop="onDelete(s.id)"
        >
          <i class="bi bi-trash3"></i>
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped lang="scss">
.session-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  overflow-y: auto;
  height: 100%;
}
.session-new-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: 1px solid var(--panel-border);
  border-radius: 8px;
  background: var(--input-bg);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 0.9rem;
}
.session-new-btn:hover { background: var(--panel-bg-hover); }
.session-empty {
  padding: 24px 12px;
  text-align: center;
  color: var(--text-muted);
  font-size: 0.85rem;
}
.session-rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.session-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
}
.session-row:hover { background: var(--panel-bg-hover); }
.session-row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  cursor: pointer;
}
.session-preview {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary);
  font-size: 0.88rem;
}
.session-time { color: var(--text-muted); font-size: 0.72rem; }
.session-delete-btn {
  flex-shrink: 0;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
}
.session-delete-btn:hover { color: var(--color-danger); background: var(--input-bg); }
</style>
