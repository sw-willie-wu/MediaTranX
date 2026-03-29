<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/tasks'
import { apiFetch } from '@/composables/useApi'

const { t } = useI18n()

const taskStore = useTaskStore()

const aiEnvLoading = ref(true)
const aiEnvReady = ref(false)
const llamaReady = ref(false)
const aiTorchIndex = ref('cpu')
const aiTorchInstalled = ref<string | null>(null)
const aiDriverVersion = ref<string | null>(null)
const aiInstallTaskId = ref<string | null>(null)
const aiInstalling = ref(false)
const aiInstalled = ref(false)

const aiInstallTask = computed(() => {
  if (!aiInstallTaskId.value) return null
  return taskStore.tasks.get(aiInstallTaskId.value) ?? null
})

const AI_CACHE_KEY = 'ai-module-cache'

function readAiCache() {
  try {
    const s = localStorage.getItem(AI_CACHE_KEY)
    return s ? JSON.parse(s) : null
  } catch { return null }
}

function writeAiCache(data: { aiEnvReady: boolean; llamaReady: boolean; torchIndex: string; driverVersion: string | null }) {
  localStorage.setItem(AI_CACHE_KEY, JSON.stringify(data))
}

async function loadAiEnvStatus() {
  const cache = readAiCache()
  if (cache) {
    aiEnvReady.value = cache.aiEnvReady
    llamaReady.value = cache.llamaReady
    aiTorchIndex.value = cache.torchIndex ?? 'cpu'
    aiTorchInstalled.value = cache.torchInstalled ?? null
    aiDriverVersion.value = cache.driverVersion ?? null
    aiEnvLoading.value = false
  }

  try {
    const res = await apiFetch('/setup/status')
    if (!res.ok) return
    const data = await res.json()
    aiEnvReady.value = data.ai_env_ready
    llamaReady.value = data.llama_ready ?? false
    aiTorchIndex.value = data.torch_index ?? 'cpu'
    aiTorchInstalled.value = data.torch_installed ?? null
    aiDriverVersion.value = data.device?.driver_version ?? null
    aiEnvLoading.value = false
    writeAiCache({
      aiEnvReady: data.ai_env_ready,
      llamaReady: data.llama_ready ?? false,
      torchIndex: data.torch_index ?? 'cpu',
      torchInstalled: data.torch_installed ?? null,
      driverVersion: data.device?.driver_version ?? null,
    })
  } catch (e) {
    console.error('Failed to load AI env status', e)
    if (!cache) aiEnvLoading.value = false
  }
}

async function installAiEnv() {
  aiInstalling.value = true
  try {
    const res = await apiFetch('/setup/initialize', { method: 'POST' })
    if (!res.ok) { aiInstalling.value = false; return }
    const { task_id } = await res.json()
    aiInstallTaskId.value = task_id
    taskStore.addTask({
      taskId: task_id,
      taskType: 'ai.setup',
      status: 'pending',
      progress: 0,
      message: t('settings.ai.preparing'),
      result: null,
      error: null,
      label: t('settings.ai.installing_toast'),
      createdAt: new Date(),
      updatedAt: new Date(),
    })
  } catch {
    aiInstalling.value = false
  }
}

watch(
  () => aiInstallTask.value?.status,
  (status) => {
    if (status === 'completed' || status === 'failed') {
      aiInstallTaskId.value = null
      aiInstalling.value = false
      if (status === 'completed') {
        aiInstalled.value = true
        aiEnvReady.value = true
        llamaReady.value = true
        writeAiCache({ aiEnvReady: true, llamaReady: true, torchIndex: aiTorchIndex.value, torchInstalled: null, driverVersion: aiDriverVersion.value })
      }
    }
  },
)

/** 從實際安裝版本解析 variant (e.g. '2.10.0+cu124' → 'cu124', '2.10.0+cpu' → 'cpu') */
function parseTorchVariant(version: string | null): string {
  if (!version) return ''
  const plus = version.indexOf('+')
  return plus >= 0 ? version.slice(plus + 1) : ''
}

const torchMismatch = computed(() => {
  if (!aiTorchInstalled.value) return false
  const installed = parseTorchVariant(aiTorchInstalled.value)
  return installed !== '' && installed !== aiTorchIndex.value
})

const coreModules = computed(() => {
  const installed = parseTorchVariant(aiTorchInstalled.value)
  const tag = installed
    ? installed.toUpperCase()
    : (aiTorchIndex.value === 'cpu' ? 'CPU' : aiTorchIndex.value.toUpperCase())
  return [
    { key: 'ai',      icon: 'bi-cpu',              name: 'Whisper / Demucs / HuggingFace', tag: '', desc: t('settings.ai.tools_desc'), ready: aiEnvReady.value },
    { key: 'torch',   icon: 'bi-lightning-charge',  name: 'PyTorch',         tag,   desc: t('settings.ai.pytorch_desc'),    ready: aiEnvReady.value, warn: torchMismatch.value },
    { key: 'llama',   icon: 'bi-translate',         name: 'llama-server',    tag,   desc: t('settings.ai.llama_desc'),      ready: llamaReady.value },
  ]
})

function restartApp() {
  ;(window as any).electron?.restart()
}

onMounted(loadAiEnvStatus)
</script>

<template>
  <h6 class="section-title">{{ $t('settings.ai.core_modules') }}</h6>

  <div class="module-list">
    <div v-for="mod in coreModules" :key="mod.key" class="module-item">
      <div class="module-info">
        <span class="module-label">{{ mod.desc }}</span>
        <span class="module-sub">
          {{ mod.name }}<template v-if="mod.tag"> ({{ mod.tag.toLowerCase() }})</template>
          <template v-if="mod.warn"> — {{ $t('settings.ai.driver_recommended') }} {{ aiTorchIndex }}, {{ $t('settings.ai.reinstall') }}</template>
        </span>
      </div>
      <span v-if="aiEnvLoading" class="module-badge badge-loading">
        <i class="bi bi-three-dots"></i>
      </span>
      <span v-else class="module-badge" :class="mod.warn ? 'badge-warn' : mod.ready ? 'badge-ok' : 'badge-off'">
        <i class="bi" :class="mod.warn ? 'bi-exclamation-triangle-fill' : mod.ready ? 'bi-check-circle-fill' : 'bi-x-circle-fill'"></i>
        {{ mod.warn ? $t('settings.ai.version_mismatch') : mod.ready ? $t('settings.ai.installed') : $t('settings.ai.not_installed') }}
      </span>
    </div>
  </div>

  <!-- Installing in progress -->
  <div v-if="!aiEnvLoading && aiInstallTask" class="ai-env-card ai-env-installing">
    <div class="ai-env-body">
      <span class="ai-env-name">{{ aiInstallTask.message }}</span>
      <div class="cuda-progress-row">
        <div class="download-progress cuda-progress-bar">
          <div class="progress-bar" :style="{ width: `${(aiInstallTask.progress * 100).toFixed(0)}%` }"></div>
        </div>
        <span class="progress-label">{{ (aiInstallTask.progress * 100).toFixed(0) }}%</span>
      </div>
    </div>
  </div>

  <!-- Installation complete, needs restart -->
  <div v-else-if="!aiEnvLoading && aiInstalled" class="ai-env-card ai-env-ok">
    <i class="bi bi-check-circle-fill"></i>
    <div class="ai-env-body">
      <span class="ai-env-name">{{ $t('settings.ai.installed_title') }}</span>
      <span class="ai-env-hint">{{ $t('settings.ai.restart_to_apply') }}</span>
      <button class="btn-success cuda-restart-btn" @click="restartApp">
        <i class="bi bi-arrow-counterclockwise"></i> {{ $t('settings.ai.restart_now') }}
      </button>
    </div>
  </div>

  <!-- All modules ready → reinstall button -->
  <div v-else-if="!aiEnvLoading && aiEnvReady && llamaReady" class="reinstall-row">
    <button class="btn-secondary reinstall-btn" :disabled="aiInstalling" @click="installAiEnv">
      <i class="bi bi-arrow-repeat"></i> {{ $t('settings.ai.reinstall_button') }}
    </button>
  </div>

  <!-- Some modules not ready → install button -->
  <div v-else-if="!aiEnvLoading && (!aiEnvReady || !llamaReady)" class="ai-env-card ai-env-warn">
    <i class="bi bi-exclamation-triangle-fill"></i>
    <div class="ai-env-body">
      <span class="ai-env-name">{{ $t('settings.ai.incomplete_title') }}</span>
      <span class="ai-env-hint">
        {{ $t('settings.ai.will_install', { index: aiTorchIndex.toUpperCase() }) }}
        <template v-if="aiDriverVersion">{{ $t('settings.ai.with_driver', { version: aiDriverVersion }) }}</template>
        <template v-else>{{ $t('settings.ai.cpu_mode') }}</template>
      </span>
      <button class="btn-primary cuda-download-btn" :disabled="aiInstalling" @click="installAiEnv">
        <i class="bi bi-download"></i> {{ $t('settings.ai.install_button') }}
      </button>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/settings-shared';
</style>

<style lang="scss" scoped>
.module-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.module-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
}

.module-info {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  flex: 1;
  min-width: 0;
}

.module-label { font-size: 0.875rem; color: var(--text-primary); font-weight: 500; }
.module-sub   { font-size: 0.75rem;  color: var(--text-muted); }

.module-badge {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.8rem;
  font-weight: 500;
  padding: 0.2rem 0.6rem;
  border-radius: 20px;
  flex-shrink: 0;

  &.badge-ok      { background: rgba(16, 185, 129, 0.12); color: #10b981; }
  &.badge-warn    { background: rgba(245, 158, 11, 0.12); color: #f59e0b; }
  &.badge-off     { background: rgba(239, 68, 68, 0.1);   color: #f87171; }
  &.badge-loading { background: transparent; color: var(--text-muted); }

  i { font-size: 0.72rem; }
}

.ai-env-card {
  display: flex;
  gap: 0.75rem;
  padding: 1rem;
  border-radius: 8px;
  border: 1px solid;
  margin-top: 0.75rem;

  > i { font-size: 1.25rem; flex-shrink: 0; margin-top: 0.1rem; }

  &.ai-env-ok         { background: rgba(16, 185, 129, 0.08); border-color: rgba(16, 185, 129, 0.25); > i { color: #10b981; } }
  &.ai-env-warn       { background: rgba(245, 158, 11, 0.08);  border-color: rgba(245, 158, 11, 0.25);  > i { color: #f59e0b; } }
  &.ai-env-installing { background: var(--input-bg); border-color: var(--input-border); }
}

.ai-env-body {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  flex: 1;
}

.ai-env-name { color: var(--text-primary); font-size: 0.875rem; font-weight: 500; }
.ai-env-hint { color: var(--text-muted); font-size: 0.75rem; strong { color: var(--text-secondary); } }

.cuda-progress-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.cuda-progress-bar { width: 200px; }

.download-progress {
  background: var(--input-bg);
  border-radius: 4px;
  overflow: hidden;
  height: 4px;
  flex: 1;
}

.progress-bar {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.3s ease;
}

.progress-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  min-width: 40px;
  text-align: right;
}

.cuda-download-btn { margin-top: 0.5rem; }

.cuda-restart-btn { margin-top: 0.25rem; }

.reinstall-row { margin-top: 0.75rem; }
</style>
