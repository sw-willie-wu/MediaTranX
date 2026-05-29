<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { useTaskStore } from '@/stores/tasks'
import { useModelStore } from '@/stores/models'
import { apiFetch } from '@/composables/useApi'
import AppModelGroupList from '@/components/common/AppModelGroupList.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import { useToast } from '@/composables/useToast'
import { useSettingsStore } from '@/stores/settings'
import AppToggle from '@/components/common/AppToggle.vue'

const { t } = useI18n()
const toast = useToast()
const route = useRoute()
const settingsStore = useSettingsStore()

const taskStore = useTaskStore()
const modelStore = useModelStore()

const activeTab = ref((route.query.category as string) || '')
const tabsRef = ref<HTMLElement | null>(null)

function onTabsWheel(e: WheelEvent) {
  if (tabsRef.value) {
    tabsRef.value.scrollLeft += e.deltaY || e.deltaX
  }
}
const downloadingTaskId = ref<Record<string, string>>({})

// ── Remote connections ──
// Source-of-truth is the store; this component just reads + dispatches actions.
import { storeToRefs } from 'pinia'
import { useRemoteModelStore, type RemoteConnection } from '@/stores/remoteModels'
const remoteModelStore = useRemoteModelStore()
const { connections } = storeToRefs(remoteModelStore)

interface RemoteModel {
  id: string
  name: string
  parameter_size?: string
  capabilities?: string[]
}

const showAddForm = ref(false)
const providerOptions = [
  { value: 'ollama', label: 'Ollama' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'gemini', label: 'Google Gemini' },
]
const _DEFAULT_ENDPOINTS: Record<string, string> = {
  ollama: 'http://localhost:11434',
  openai: 'https://api.openai.com',
  gemini: 'https://generativelanguage.googleapis.com',
}
const newConn = ref({ provider: 'ollama', name: '', endpoint: 'http://localhost:11434', api_key: '' })
watch(() => newConn.value.provider, (p) => {
  newConn.value.endpoint = _DEFAULT_ENDPOINTS[p] || ''
})
const testingConn = ref(false)
const testResult = ref<{ connected: boolean; models: RemoteModel[] } | null>(null)
const expandedConnId = ref<number | null>(null)
const editingConnId = ref<number | null>(null)
const editConn = ref({ name: '', endpoint: '', api_key: '' })
const showEditKey = ref(false)
const showNewKey = ref(false)

async function onCopyKey(id: number) {
  // Copy-only: fetch the plaintext once and write it straight to the clipboard.
  // The key is never displayed on screen (no reveal/visible state).
  const k = await remoteModelStore.revealKey(id)
  if (!k) {
    toast.show(t('settings.models.reveal_failed'), { type: 'error' })
    return
  }
  try {
    await navigator.clipboard.writeText(k)
    toast.show(t('settings.models.key_copied'), { type: 'success' })
  } catch {
    toast.show(t('settings.models.copy_failed'), { type: 'error' })
  }
}

async function addConnection() {
  const ok = await remoteModelStore.addConnection(newConn.value)
  if (ok) {
    showAddForm.value = false
    newConn.value = { provider: 'ollama', name: '', endpoint: _DEFAULT_ENDPOINTS['ollama'], api_key: '' }
    testResult.value = null
  }
}

async function deleteConnection(id: number) {
  await remoteModelStore.deleteConnection(id)
}

function startEdit(conn: RemoteConnection) {
  editingConnId.value = conn.id
  // api_key is write-only: never prefilled (the server no longer returns it).
  // Empty field on save = keep the stored key.
  editConn.value = { name: conn.name, endpoint: conn.endpoint, api_key: '' }
}

function cancelEdit() {
  editingConnId.value = null
}

async function saveEdit(id: number) {
  const payload: { name: string; endpoint: string; api_key?: string } = {
    name: editConn.value.name,
    endpoint: editConn.value.endpoint,
  }
  // Only send api_key when the user typed a new one — an empty field means
  // "keep the existing key" (omitting it lets the backend preserve it).
  if (editConn.value.api_key) payload.api_key = editConn.value.api_key
  const ok = await remoteModelStore.updateConnection(id, payload)
  if (ok) {
    editingConnId.value = null
  }
}

async function toggleConnection(conn: RemoteConnection) {
  await remoteModelStore.toggleConnection(conn.id, !conn.enabled)
}

async function toggleExpand(conn: RemoteConnection) {
  if (expandedConnId.value === conn.id) {
    expandedConnId.value = null
    return
  }
  expandedConnId.value = conn.id
  if (!remoteModelStore.connModels[conn.id]) {
    await remoteModelStore.fetchConnModels(conn)
  }
}

function refreshConnModels(conn: RemoteConnection) {
  remoteModelStore.clearConnCache(conn.id)
  remoteModelStore.fetchConnModels(conn)
}

async function testConnection() {
  testingConn.value = true
  testResult.value = null
  try {
    const res = await apiFetch('/setup/remote/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider: newConn.value.provider,
        endpoint: newConn.value.endpoint,
        api_key: newConn.value.api_key || null,
      }),
    })
    if (res.ok) testResult.value = await res.json()
  } catch {
    testResult.value = { connected: false, models: [] }
  } finally {
    testingConn.value = false
  }
}

const downloadProgress = computed(() => {
  const result: Record<string, number> = {}
  for (const [id, taskId] of Object.entries(downloadingTaskId.value)) {
    result[id] = taskStore.tasks.get(taskId)?.progress ?? 0
  }
  return result
})

// 初始化：載入模型後選中第一個 tab
watch(() => modelStore.categories, (cats) => {
  if (cats.length && !activeTab.value) {
    activeTab.value = cats[0].key
  }
}, { immediate: true })

async function downloadItem(id: string) {
  const res = await apiFetch('/setup/models/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  })
  if (!res.ok) { console.error('Download request failed:', res.statusText); return }
  const { task_id } = await res.json()
  downloadingTaskId.value[id] = task_id

  taskStore.addTask({
    taskId: task_id,
    taskType: 'setup.download',
    status: 'pending',
    progress: 0,
    message: `${t('settings.models.title')} ${id}`,
    result: null,
    error: null,
    label: `${t('settings.models.title')} ${id}`,
    createdAt: new Date(),
    updatedAt: new Date(),
  })
}

async function removeItem(id: string) {
  const res = await apiFetch('/setup/models/remove', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  })
  if (res.ok) modelStore.setDownloaded(id, false)
}

watch(
  () => Object.entries(downloadingTaskId.value).map(([, taskId]) =>
    taskStore.tasks.get(taskId)?.status
  ),
  () => {
    for (const [itemId, taskId] of Object.entries(downloadingTaskId.value)) {
      const task = taskStore.tasks.get(taskId)
      if (task && (task.status === 'completed' || task.status === 'failed')) {
        delete downloadingTaskId.value[itemId]
        if (task.status === 'completed') {
          modelStore.setDownloaded(itemId, true)
          toast.show(t('settings.models.download_success', { id: itemId }), { type: 'success' })
        } else {
          toast.show(t('settings.models.download_failed', { id: itemId, error: task.error || '' }), { type: 'error' })
        }
      }
    }
  },
)

onMounted(() => {
  modelStore.fetchModels()
  remoteModelStore.fetchAll()
})
</script>

<template>
  <!-- Display settings -->
  <h6 class="section-title">{{ $t('settings.models.display_title') }}</h6>
  <div class="setting-item">
    <AppToggle :modelValue="settingsStore.showAllModels" @update:modelValue="settingsStore.setShowAllModels">
      {{ $t('settings.models.show_all_models') }}
    </AppToggle>
    <p class="download-hint"><i class="bi bi-info-circle"></i> {{ $t('settings.models.show_all_models_hint') }}</p>
  </div>

  <!-- Model list -->
  <h6 class="section-title" style="margin-top: 1.5rem;">{{ $t('settings.models.title') }}</h6>
  <p class="download-hint"><i class="bi bi-info-circle"></i> {{ $t('settings.models.hint') }}</p>

  <div v-if="modelStore.loading && !modelStore.loaded" class="models-loading">
    <div class="spinner"></div>
    <span>{{ $t('settings.models.loading') }}</span>
  </div>

  <template v-else-if="modelStore.loaded">
    <!-- Category tabs -->
    <div class="category-tabs" ref="tabsRef" @wheel.prevent="onTabsWheel">
      <button
        v-for="cat in modelStore.categories"
        :key="cat.key"
        class="category-tab"
        :class="{ 'is-active': activeTab === cat.key }"
        @click="activeTab = cat.key"
      >{{ $t(`settings.models.category_${cat.key}`) }}</button>
      <button
        class="category-tab"
        :class="{ 'is-active': activeTab === 'remote' }"
        @click="activeTab = 'remote'"
      >{{ $t('settings.remote.title') }}</button>
    </div>

    <!-- Local model tab content -->
    <template v-if="activeTab !== 'remote'">
      <AppModelGroupList
        :items="modelStore.byCategory(activeTab)"
        :downloadingTaskId="downloadingTaskId"
        :downloadProgress="downloadProgress"
        @download="downloadItem"
        @remove="removeItem"
      />

      <button class="btn-secondary refresh-btn" @click="modelStore.fetchModels()">
        <i class="bi bi-arrow-clockwise"></i> {{ $t('settings.models.refresh') }}
      </button>
    </template>

  <template v-if="activeTab === 'remote'">
    <!-- Connection list -->
    <div v-if="connections.length" class="conn-list">
      <div v-for="conn in connections" :key="conn.id" class="conn-card" :class="{ expanded: expandedConnId === conn.id }">
        <div class="conn-header" @click="toggleExpand(conn)">
          <div class="conn-title">
            <span class="conn-name">{{ conn.name }}</span>
            <span class="conn-endpoint">{{ conn.endpoint }}</span>
          </div>
          <div class="conn-actions" @click.stop>
            <button v-if="conn.has_api_key" class="btn-secondary btn-sm" @click="onCopyKey(conn.id)" :title="$t('settings.models.copy_key')">
              <i class="bi bi-clipboard"></i>
            </button>
            <button class="btn-secondary btn-sm" @click="refreshConnModels(conn)" :title="$t('settings.remote.refresh')">
              <i class="bi bi-arrow-clockwise"></i>
            </button>
            <button class="btn-secondary btn-sm" @click.stop="startEdit(conn)" :title="$t('settings.remote.edit')">
              <i class="bi bi-pencil"></i>
            </button>
            <button class="btn-secondary btn-sm btn-conn-toggle" :class="{ 'is-on': conn.enabled }" @click="toggleConnection(conn)" :title="conn.enabled ? 'Disable' : 'Enable'">
              <i :class="conn.enabled ? 'bi bi-toggle-on' : 'bi bi-toggle-off'"></i>
            </button>
            <button class="btn-secondary btn-sm" @click="deleteConnection(conn.id)" :title="$t('settings.remote.delete')">
              <i class="bi bi-trash"></i>
            </button>
            <i class="bi conn-chevron" :class="expandedConnId === conn.id ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
          </div>
        </div>
        <!-- 編輯表單 -->
        <div v-if="editingConnId === conn.id" class="conn-edit-form">
          <div class="form-group">
            <label>{{ $t('settings.models.remote_name') }}</label>
            <input class="form-input" v-model="editConn.name" />
          </div>
          <div class="form-group">
            <label>Endpoint</label>
            <input class="form-input" v-model="editConn.endpoint" />
          </div>
          <div class="form-group">
            <label>API Key</label>
            <div class="input-with-eye">
              <input class="form-input" v-model="editConn.api_key" :type="showEditKey ? 'text' : 'password'" :placeholder="conn.has_api_key && conn.key_hint ? conn.key_hint : 'sk-...'" />
              <button class="eye-btn" @mousedown="showEditKey = true" @mouseup="showEditKey = false" @mouseleave="showEditKey = false">
                <i :class="showEditKey ? 'bi bi-eye' : 'bi bi-eye-slash'"></i>
              </button>
            </div>
          </div>
          <div class="conn-edit-actions">
            <button class="btn-secondary btn-sm" @click="cancelEdit">{{ $t('common.cancel') }}</button>
            <button class="btn-primary btn-sm" @click="saveEdit(conn.id)">{{ $t('common.save') }}</button>
          </div>
        </div>
        <div v-if="expandedConnId === conn.id && editingConnId !== conn.id" class="conn-models">
          <div v-if="remoteModelStore.connLoading[conn.id]" class="conn-models-loading">
            <div class="spinner"></div>
            <span>{{ $t('settings.models.loading') }}</span>
          </div>
          <template v-else-if="remoteModelStore.connModels[conn.id]?.length">
            <div v-for="m in remoteModelStore.connModels[conn.id]" :key="m.id" class="conn-model-item">
              <div class="conn-model-left">
                <span class="conn-model-name">{{ m.name }}</span>
                <div v-if="m.capabilities?.length" class="conn-model-caps">
                  <span v-for="cap in m.capabilities" :key="cap" class="cap-badge" :class="`cap-${cap}`">{{ cap }}</span>
                </div>
              </div>
              <div class="conn-model-right">
                <span v-if="m.parameter_size" class="conn-model-size">{{ m.parameter_size }}</span>
                <button class="btn-toggle-model" :class="{ 'is-on': remoteModelStore.enabledIds.has(`${conn.provider}:${m.id}`) }" @click="remoteModelStore.toggleEnabled(`${conn.provider}:${m.id}`)">
                  <i :class="remoteModelStore.enabledIds.has(`${conn.provider}:${m.id}`) ? 'bi bi-toggle-on' : 'bi bi-toggle-off'"></i>
                </button>
              </div>
            </div>
          </template>
          <p v-else class="conn-models-empty">{{ $t('settings.remote.no_models') }}</p>
        </div>
      </div>
    </div>
    <p v-else class="conn-empty">{{ $t('settings.remote.no_connections') }}</p>

    <!-- Add connection form -->
    <button v-if="!showAddForm" class="btn-secondary" @click="showAddForm = true">
      <i class="bi bi-plus-circle"></i> {{ $t('settings.remote.add') }}
    </button>

    <div v-if="showAddForm" class="conn-form">
      <div class="form-group">
        <label>{{ $t('settings.remote.provider') }}</label>
        <AppSelect v-model="newConn.provider" :options="providerOptions" />
      </div>
      <div class="form-group">
        <label>{{ $t('settings.remote.name') }}</label>
        <input v-model="newConn.name" class="form-input" :placeholder="$t('settings.remote.name_placeholder')" />
      </div>
      <div class="form-group">
        <label>{{ $t('settings.remote.endpoint') }}</label>
        <input v-model="newConn.endpoint" class="form-input" placeholder="http://localhost:11434" />
      </div>
      <div class="form-group">
        <label>API Key <span v-if="newConn.provider === 'ollama'" class="label-optional">({{ $t('common.optional') }})</span></label>
        <div class="input-with-eye">
          <input v-model="newConn.api_key" class="form-input" :type="showNewKey ? 'text' : 'password'" :placeholder="newConn.provider === 'ollama' ? '' : 'sk-...'" />
          <button class="eye-btn" @mousedown="showNewKey = true" @mouseup="showNewKey = false" @mouseleave="showNewKey = false">
            <i :class="showNewKey ? 'bi bi-eye' : 'bi bi-eye-slash'"></i>
          </button>
        </div>
      </div>

      <!-- Test result -->
      <div v-if="testResult" class="test-result" :class="testResult.connected ? 'success' : 'error'">
        <i :class="testResult.connected ? 'bi bi-check-circle' : 'bi bi-x-circle'"></i>
        <span v-if="testResult.connected">
          {{ $t('settings.remote.connected') }} · {{ testResult.models.length }} {{ $t('settings.remote.models_available') }}
        </span>
        <span v-else>{{ $t('settings.remote.connection_failed') }}</span>
      </div>

      <div class="conn-form-actions">
        <button class="btn-secondary" @click="testConnection" :disabled="testingConn || !newConn.endpoint">
          <i class="bi bi-plug"></i> {{ $t('settings.remote.test') }}
        </button>
        <button class="btn-primary" @click="addConnection" :disabled="!newConn.name || !newConn.endpoint">
          <i class="bi bi-save"></i> {{ $t('settings.remote.save') }}
        </button>
        <button class="btn-secondary" @click="showAddForm = false; testResult = null">
          {{ $t('common.cancel') }}
        </button>
      </div>
    </div>
  </template>
  </template>
</template>

<style lang="scss">
@use '@/styles/settings-shared';
</style>

<style lang="scss" scoped>
.models-loading {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.refresh-btn { margin-top: 1rem; }

.download-hint {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-bottom: 0.5rem;
}

// ── Category tabs ─────────────────────────────────────────────
.category-tabs {
  display: flex;
  gap: 0.25rem;
  margin-bottom: 1rem;
  padding: 0.25rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  overflow-x: auto;
}

.category-tab {
  flex: 1 0 0%;
  min-width: max-content;
  padding: 0.4rem 0.75rem;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 0.8rem;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;

  &:hover:not(.is-active) {
    color: var(--text-secondary);
    background: var(--panel-bg-hover);
  }

  &.is-active {
    background: var(--color-primary);
    color: #fff;
    font-weight: 500;
  }
}

// ── Remote connections ──────────────────────────────────────
.conn-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.conn-card {
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  overflow: hidden;
  transition: border-color 0.15s ease;

  &.expanded {
    border-color: var(--color-primary);
  }
}

.conn-edit-form {
  padding: 0.75rem;
  border-top: 1px solid var(--input-border);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    label { font-size: 0.8rem; color: var(--text-secondary); }
  }
}

.input-with-eye {
  position: relative;
  display: flex;
  align-items: center;

  .form-input { flex: 1; padding-right: 2.2rem; }
}

.eye-btn {
  position: absolute;
  right: 0.5rem;
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0.25rem;
  font-size: 1rem;
  transition: color 0.15s ease;

  &:hover { color: var(--text-primary); }
}

.conn-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.conn-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.6rem 0.75rem;
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover { background: var(--panel-bg-hover); }
}

.conn-title {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.conn-name {
  color: var(--text-primary);
  font-weight: 500;
  font-size: 0.85rem;
}

.conn-endpoint {
  color: var(--text-muted);
  font-size: 0.7rem;
}

.conn-actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.conn-chevron {
  color: var(--text-muted);
  font-size: 0.75rem;
  margin-left: 0.25rem;
}

.conn-models {
  border-top: 1px solid var(--input-border);
  padding: 0.5rem;
}

.conn-models-loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  color: var(--text-muted);
  font-size: 0.8rem;
}

.conn-model-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.35rem 0.5rem;
  border-radius: 6px;
  transition: background 0.15s ease;

  &:hover { background: var(--panel-bg-hover); }
}

.conn-model-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.conn-model-name {
  color: var(--text-primary);
  font-size: 0.8rem;
}

.conn-model-caps {
  display: flex;
  gap: 0.25rem;
}

.cap-badge {
  font-size: 0.65rem;
  padding: 0.15rem 0.45rem;
  border-radius: 50rem;
  font-weight: 600;

  &.cap-text {
    color: var(--color-info);
    background: color-mix(in srgb, var(--color-info) 20%, transparent);
  }
  &.cap-vision {
    color: var(--color-success);
    background: color-mix(in srgb, var(--color-success) 20%, transparent);
  }
  &.cap-embedding {
    color: var(--color-warning);
    background: color-mix(in srgb, var(--color-warning) 20%, transparent);
  }
  &.cap-tools {
    color: var(--color-accent);
    background: color-mix(in srgb, var(--color-accent) 20%, transparent);
  }
}

.conn-model-right {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.conn-model-size {
  color: var(--text-muted);
  font-size: 0.7rem;
}

.btn-toggle-model {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1.1rem;
  color: var(--text-muted);
  padding: 0;
  transition: color 0.15s ease;

  &.is-on {
    color: var(--color-success);
  }
}

.conn-models-empty {
  color: var(--text-muted);
  font-size: 0.8rem;
  padding: 0.5rem;
  text-align: center;
}

.conn-empty {
  color: var(--text-muted);
  font-size: 0.8rem;
  margin-bottom: 1rem;
}

.conn-form {
  margin-top: 0.75rem;
  padding: 1rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.conn-form .form-group {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;

  label {
    font-size: 0.75rem;
    color: var(--text-secondary);
  }
}

.conn-form-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.test-result {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.8rem;
  padding: 0.4rem 0.6rem;
  border-radius: 6px;

  &.success {
    color: var(--color-success);
    background: color-mix(in srgb, var(--color-success) 10%, transparent);
  }

  &.error {
    color: var(--color-danger);
    background: color-mix(in srgb, var(--color-danger) 10%, transparent);
  }
}

.btn-conn-toggle.is-on {
  color: var(--color-success);
}

.btn-sm {
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
}
</style>
