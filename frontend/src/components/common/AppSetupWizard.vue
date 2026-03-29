<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/tasks'
import { useSettingsStore } from '@/stores/settings'
import { apiFetch } from '@/composables/useApi'

const emit = defineEmits<{
  (e: 'close'): void
}>()

const { t } = useI18n()
const taskStore = useTaskStore()
const settingsStore = useSettingsStore()

type WizardState = 'checking' | 'idle' | 'installing' | 'completed' | 'error'
const state = ref<WizardState>('checking')
const taskId = ref<string | null>(null)
const errorMessage = ref('')

interface StatusData {
  ai_env_ready: boolean
  torch_index: string
  device: {
    device_name: string
    memory_total: number | null
    has_nvidia_gpu: boolean
    driver_version: string | null
  }
}
const statusData = ref<StatusData | null>(null)

const task = computed(() => taskId.value ? taskStore.tasks.get(taskId.value) : null)
const progress = computed(() => Math.round((task.value?.progress ?? 0) * 100))
const progressMessage = computed(() => task.value?.message ?? t('settings.ai.preparing'))

const torchLabel = computed(() => {
  const idx = statusData.value?.torch_index ?? 'cpu'
  if (idx === 'cpu') return 'CPU'
  return idx.toUpperCase()
})

const downloadSize = computed(() => {
  const idx = statusData.value?.torch_index ?? 'cpu'
  return idx === 'cpu' ? '~250 MB' : '~2.7 GB'
})

const gpuName = computed(() => statusData.value?.device.device_name ?? null)

const vramText = computed(() => {
  const bytes = statusData.value?.device.memory_total
  if (!bytes) return ''
  return `${(bytes / (1024 ** 3)).toFixed(0)} GB`
})

const driverVersion = computed(() => statusData.value?.device.driver_version ?? null)

const hasNvidiaGpu = computed(() => statusData.value?.device.has_nvidia_gpu ?? false)

async function checkStatus() {
  // 先讀快取，快速決定初始狀態
  try {
    const cached = localStorage.getItem('ai-module-cache')
    if (cached) {
      const c = JSON.parse(cached)
      if (c.aiEnvReady && c.llamaReady) { emit('close'); return }
      // 有快取且未就緒，直接進 idle（用快取資料填 statusData）
      statusData.value = {
        ai_env_ready: c.aiEnvReady,
        torch_index: c.torchIndex ?? 'cpu',
        device: { device_name: c.deviceName ?? 'CPU', memory_total: c.memoryTotal ?? null, has_nvidia_gpu: !!c.driverVersion, driver_version: c.driverVersion ?? null },
      }
      state.value = 'idle'
    }
  } catch { /* ignore */ }

  // 背景向後端確認最新狀態
  try {
    const res = await apiFetch('/setup/status')
    const data: StatusData = await res.json()
    statusData.value = data
    if (data.ai_env_ready && (data as any).llama_ready !== false) {
      emit('close')
    } else {
      state.value = 'idle'
    }
  } catch {
    if (state.value === 'checking') state.value = 'idle'
  }
}

async function startInstall() {
  state.value = 'installing'
  try {
    const res = await apiFetch('/setup/initialize', { method: 'POST' })
    if (!res.ok) throw new Error(t('toast.submit_error'))
    const { task_id } = await res.json()
    taskId.value = task_id
    taskStore.addTask({
      taskId: task_id,
      taskType: 'ai.setup',
      status: 'pending',
      progress: 0,
      message: t('settings.ai.preparing'),
      result: null,
      error: null,
      label: t('settings.ai.reinstall_button'),
      createdAt: new Date(),
      updatedAt: new Date(),
    })
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : t('wizard.error_title')
    state.value = 'error'
  }
}

watch(
  () => task.value?.status,
  (status) => {
    if (status === 'completed') {
      state.value = 'completed'
      settingsStore.loadDeviceInfo()
    }
    else if (status === 'failed') {
      errorMessage.value = task.value?.error ?? t('document.translate.install_error')
      state.value = 'error'
    }
  },
)

function restartApp() {
  ;(window as any).electron?.restart()
}

onMounted(() => {
  checkStatus()
})
</script>

<template>
  <Teleport to="body">
    <div class="wizard-overlay">
      <div class="wizard-card">

        <!-- Checking -->
        <template v-if="state === 'checking'">
          <div class="wizard-icon spin">
            <i class="bi bi-arrow-repeat"></i>
          </div>
          <p class="wizard-subtitle">{{ $t('wizard.checking') }}</p>
        </template>

        <!-- Idle: prompt to install -->
        <template v-else-if="state === 'idle'">
          <div class="wizard-icon">
            <i class="bi bi-boxes"></i>
          </div>
          <h3 class="wizard-title">{{ $t('wizard.title') }}</h3>

          <div class="pkg-list">
            <p class="pkg-list-label">{{ $t('wizard.will_install') }}</p>
            <div class="pkg-item">
              <i class="bi bi-cpu"></i>
              <div class="pkg-info">
                <span class="pkg-name">Whisper / Demucs / HuggingFace</span>
                <span class="pkg-desc">{{ $t('settings.ai.tools_desc') }}</span>
              </div>
            </div>
            <div class="pkg-item">
              <i class="bi bi-lightning-charge"></i>
              <div class="pkg-info">
                <span class="pkg-name">{{ $t('wizard.pytorch') }} <span class="pkg-tag">{{ torchLabel }}</span></span>
                <span class="pkg-desc">{{ $t('settings.ai.pytorch_desc') }}</span>
              </div>
            </div>
            <div class="pkg-item">
              <i class="bi bi-translate"></i>
              <div class="pkg-info">
                <span class="pkg-name">{{ $t('wizard.llama_cpp') }} <span class="pkg-tag">{{ torchLabel }}</span></span>
                <span class="pkg-desc">{{ $t('settings.ai.llama_desc') }}</span>
              </div>
            </div>
            <div class="pkg-size-row">
              <i class="bi bi-hdd"></i>
              <span>{{ $t('wizard.estimated_download') }} <strong>{{ downloadSize }}</strong></span>
            </div>
          </div>

          <div class="wizard-actions">
            <button class="btn-primary" @click="startInstall">
              <i class="bi bi-download me-1"></i>{{ $t('wizard.install_now') }}
            </button>
            <button class="btn-secondary" @click="emit('close')">{{ $t('wizard.install_later') }}</button>
          </div>
        </template>

        <!-- Installing -->
        <template v-else-if="state === 'installing'">
          <div class="wizard-icon installing">
            <i class="bi bi-boxes"></i>
          </div>
          <h3 class="wizard-title">{{ $t('wizard.installing_title') }}</h3>
          <p class="wizard-subtitle">{{ $t('wizard.version_label') }}{{ torchLabel }} · {{ downloadSize }}</p>

          <div class="progress-wrap">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: `${progress}%` }"></div>
            </div>
            <div class="progress-info">
              <span class="progress-msg">{{ progressMessage }}</span>
              <span class="progress-pct">{{ progress }}%</span>
            </div>
          </div>

          <p class="wizard-hint">{{ $t('wizard.installing_hint') }}</p>

          <div class="wizard-actions">
            <button class="btn-secondary" @click="emit('close')">
              <i class="bi bi-arrow-right me-1"></i>{{ $t('wizard.continue_using') }}
            </button>
          </div>
        </template>

        <!-- Completed -->
        <template v-else-if="state === 'completed'">
          <div class="wizard-icon success">
            <i class="bi bi-check-circle-fill"></i>
          </div>
          <h3 class="wizard-title">{{ $t('wizard.completed_title') }}</h3>
          <p class="wizard-hint">{{ $t('wizard.completed_hint') }}</p>
          <div class="wizard-actions">
            <button class="btn-primary" @click="restartApp()">
              <i class="bi bi-arrow-counterclockwise me-1"></i>{{ $t('wizard.restart_now') }}
            </button>
            <button class="btn-secondary" @click="emit('close')">{{ $t('wizard.restart_later') }}</button>
          </div>
        </template>

        <!-- Error -->
        <template v-else-if="state === 'error'">
          <div class="wizard-icon error">
            <i class="bi bi-x-circle-fill"></i>
          </div>
          <h3 class="wizard-title">{{ $t('wizard.error_title') }}</h3>
          <p class="wizard-hint error-text">{{ errorMessage }}</p>
          <div class="wizard-actions">
            <button class="btn-primary" @click="startInstall">
              <i class="bi bi-arrow-clockwise me-1"></i>{{ $t('common.retry') }}
            </button>
            <button class="btn-secondary" @click="emit('close')">{{ $t('common.close') }}</button>
          </div>
        </template>

      </div>
    </div>
  </Teleport>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';
</style>

<style lang="scss" scoped>
.wizard-overlay {
  position: fixed;
  inset: 0;
  z-index: 9000;
  background: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to   { opacity: 1; }
}

.wizard-card {
  background: var(--panel-bg, #1e2030);
  border: 1px solid var(--panel-border, rgba(255,255,255,0.1));
  border-radius: 16px;
  padding: 2.5rem 2rem;
  width: 420px;
  max-width: calc(100vw - 2rem);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.25rem;
  box-shadow: 0 24px 64px rgba(0,0,0,0.5);
  animation: slideUp 0.25s ease;
}

@keyframes slideUp {
  from { transform: translateY(16px); opacity: 0; }
  to   { transform: translateY(0);    opacity: 1; }
}

.wizard-icon {
  width: 64px;
  height: 64px;
  border-radius: 16px;
  background: rgba(96, 165, 250, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2rem;
  color: var(--color-primary, #60a5fa);

  &.success {
    background: rgba(16, 185, 129, 0.15);
    color: #10b981;
  }
  &.error {
    background: rgba(239, 68, 68, 0.15);
    color: #ef4444;
  }
  &.installing i {
    animation: pulse 1.5s ease-in-out infinite;
  }
  &.spin i {
    animation: spin 1s linear infinite;
  }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.5; }
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

.wizard-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  text-align: center;
}

.wizard-subtitle {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin: -0.5rem 0 0;
  text-align: center;
}

.wizard-hint {
  font-size: 0.82rem;
  color: var(--text-muted);
  text-align: center;
  line-height: 1.6;
  margin: 0;

  &.error-text { color: #ef4444; }
}


.pkg-size-row {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.45rem 0.75rem 0;
  margin-top: 0.2rem;
  border-top: 1px solid var(--input-border, rgba(255,255,255,0.08));
  font-size: 0.8rem;
  color: var(--text-muted);

  i { color: var(--text-muted); font-size: 0.85rem; }
  strong { color: var(--color-primary, #60a5fa); }
}

.pkg-list {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.pkg-list-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin: 0 0 0.4rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.pkg-item {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.45rem 0.75rem;
  border-radius: 8px;
  background: var(--input-bg, rgba(255,255,255,0.04));

  > i {
    font-size: 0.9rem;
    color: var(--color-primary, #60a5fa);
    flex-shrink: 0;
    width: 1rem;
    text-align: center;
  }
}

.pkg-info {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  flex: 1;
  min-width: 0;
}

.pkg-name {
  font-size: 0.83rem;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
}

.pkg-tag {
  font-size: 0.7rem;
  font-weight: 600;
  background: rgba(96, 165, 250, 0.15);
  color: var(--color-primary, #60a5fa);
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  letter-spacing: 0.02em;
}

.pkg-desc {
  font-size: 0.76rem;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.progress-wrap {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.progress-bar {
  width: 100%;
  height: 6px;
  background: var(--input-border, rgba(255,255,255,0.1));
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary, #60a5fa), #818cf8);
  border-radius: 3px;
  transition: width 0.4s ease;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  font-size: 0.78rem;
}

.progress-msg { color: var(--text-muted); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.progress-pct { color: var(--text-secondary); flex-shrink: 0; margin-left: 0.5rem; }

.wizard-actions {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  width: 100%;
}

.btn-primary {
  width: 100%;
  padding: 0.65rem 1rem;
  font-size: 0.9rem;
}

.btn-secondary {
  width: 100%;
  padding: 0.6rem 1rem;
  font-size: 0.85rem;
}
</style>
