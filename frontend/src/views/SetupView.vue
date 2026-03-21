<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { apiFetch, getApiBase } from '@/composables/useApi'

const { t } = useI18n()
const router = useRouter()
const taskStore = useTaskStore()
const toast = useToast()

const systemStatus = ref<any>(null)
const isInstalling = ref(false)
const installLog = ref<string[]>([])
const progress = ref(0)
const currentStep = ref('')

// 獲取系統狀態
async function fetchStatus() {
  try {
    const res = await apiFetch('/setup/status')
    systemStatus.value = await res.json()
  } catch (e) {
    console.error('Failed to fetch system status', e)
  }
}

// 開始初始化環境
async function startSetup() {
  if (isInstalling.value) return
  isInstalling.value = true
  installLog.value = []
  progress.value = 0
  
  try {
    const res = await apiFetch('/setup/initialize', { method: 'POST' })
    const { task_id } = await res.json()
    
    // 訂閱 SSE 進度
    subscribeToSetup(task_id)
  } catch (e) {
    toast.show(t('wizard.start_install_failed'), { type: 'error' })
    isInstalling.value = false
  }
}

function subscribeToSetup(taskId: string) {
  const eventSource = new EventSource(`${getApiBase()}/tasks/${taskId}/progress`)
  
  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data)
    
    if (data.stage === 'processing') {
      progress.value = data.progress * 100
      currentStep.value = data.message
      if (data.message.startsWith('UV:')) {
        installLog.value.push(data.message.replace('UV: ', ''))
        // 保持日誌滾動到底部
        nextTick(() => {
          const el = document.querySelector('.log-container')
          if (el) el.scrollTop = el.scrollHeight
        })
      }
    } else if (data.stage === 'completed') {
      toast.show(t('wizard.install_complete_toast'), { type: 'success' })
      isInstalling.value = false
      eventSource.close()
      fetchStatus()
    } else if (data.stage === 'error') {
      toast.show(t('wizard.install_error_toast', { message: data.message }), { type: 'error' })
      isInstalling.value = false
      eventSource.close()
    }
  }
  
  eventSource.onerror = () => {
    eventSource.close()
    isInstalling.value = false
  }
}

function nextTick(fn: () => void) {
  setTimeout(fn, 0)
}

onMounted(() => {
  fetchStatus()
})
</script>

<template>
  <div class="setup-view">
    <div class="header">
      <h1>{{ $t('wizard.manager_title') }}</h1>
      <p class="subtitle">{{ $t('wizard.manager_subtitle') }}</p>
    </div>

    <div class="status-grid" v-if="systemStatus">
      <div class="status-card" :class="{ ready: systemStatus.ai_env_ready }">
        <div class="card-icon">
          <i class="bi" :class="systemStatus.ai_env_ready ? 'bi-check-circle-fill' : 'bi-exclamation-triangle-fill'"></i>
        </div>
        <div class="card-content">
          <h3>{{ $t('wizard.env_status') }}</h3>
          <p>{{ systemStatus.ai_env_ready ? $t('wizard.env_ready') : $t('wizard.env_not_ready') }}</p>
        </div>
      </div>

      <div class="status-card">
        <div class="card-icon"><i class="bi bi-gpu-card"></i></div>
        <div class="card-content">
          <h3>{{ $t('wizard.detected_hardware') }}</h3>
          <p>{{ systemStatus.device.device_name }}</p>
          <small v-if="systemStatus.device.has_nvidia_gpu" class="text-success">
            {{ $t('wizard.cuda_supported') }}
          </small>
          <small v-else class="text-warning">
            {{ $t('wizard.no_gpu_cpu_mode') }}
          </small>
        </div>
      </div>
    </div>

    <div class="setup-panel" v-if="!systemStatus?.ai_env_ready || isInstalling">
      <div class="setup-action" v-if="!isInstalling">
        <h2>{{ $t('wizard.install_env_title') }}</h2>
        <p>{{ $t('wizard.install_env_desc') }}</p>
        <button class="btn-primary large" @click="startSetup">{{ $t('wizard.install_one_click') }}</button>
      </div>

      <div class="install-progress" v-else>
        <div class="progress-info">
          <span class="step">{{ currentStep }}</span>
          <span class="percent">{{ Math.round(progress) }}%</span>
        </div>
        <div class="progress-bar-bg">
          <div class="progress-bar-fill" :style="{ width: progress + '%' }"></div>
        </div>
        
        <div class="log-container">
          <div v-for="(line, i) in installLog" :key="i" class="log-line">
            <span class="timestamp">[{{ new Date().toLocaleTimeString() }}]</span> {{ line }}
          </div>
        </div>
      </div>
    </div>

    <div class="ready-panel" v-else>
      <i class="bi bi-stars"></i>
      <h2>{{ $t('wizard.all_ready_title') }}</h2>
      <p>{{ $t('wizard.all_ready_desc') }}</p>
      <button class="btn-secondary" @click="router.push('/')">{{ $t('wizard.go_home') }}</button>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.setup-view {
  padding: 2rem;
  max-width: 1000px;
  margin: 0 auto;
  color: var(--text-primary);
}

.header {
  text-align: center;
  margin-bottom: 3rem;
  h1 { font-size: 2.5rem; margin-bottom: 0.5rem; }
  .subtitle { color: var(--text-secondary); font-size: 1.1rem; }
}

.status-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.status-card {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  padding: 1.5rem;
  display: flex;
  align-items: center;
  gap: 1.2rem;
  transition: all 0.3s ease;

  &.ready { border-color: var(--color-success); }
  
  .card-icon {
    font-size: 2.2rem;
    color: var(--text-secondary);
  }
  
  &.ready .card-icon { color: var(--color-success); }
  
  h3 { font-size: 1.1rem; margin-bottom: 0.2rem; }
  p { font-weight: 600; color: var(--text-primary); }
  small { display: block; margin-top: 0.2rem; }
}

.setup-panel {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: 16px;
  padding: 3rem;
  text-align: center;
  
  h2 { margin-bottom: 1rem; }
  p { color: var(--text-secondary); margin-bottom: 2rem; max-width: 600px; margin-left: auto; margin-right: auto; }
}

.btn-primary.large {
  padding: 1rem 3rem;
  font-size: 1.2rem;
  border-radius: 50px;
  box-shadow: 0 4px 15px rgba(var(--color-primary-rgb), 0.3);
  &:hover { transform: translateY(-2px); filter: brightness(1.1); }
}

.install-progress {
  text-align: left;
  .progress-info { display: flex; justify-content: space-between; margin-bottom: 0.8rem; font-weight: 600; }
  .progress-bar-bg { height: 10px; background: rgba(255,255,255,0.1); border-radius: 5px; margin-bottom: 1.5rem; overflow: hidden; }
  .progress-bar-fill { height: 100%; background: var(--color-primary); transition: width 0.3s ease; }
}

.log-container {
  background: #000;
  border-radius: 8px;
  padding: 1rem;
  height: 250px;
  overflow-y: auto;
  font-family: monospace;
  font-size: 0.85rem;
  color: #00ff00;
  .log-line { margin-bottom: 0.3rem; line-height: 1.4; }
  .timestamp { color: #888; margin-right: 0.5rem; }
}

.ready-panel {
  text-align: center;
  padding: 4rem;
  i { font-size: 5rem; color: var(--color-accent); margin-bottom: 1.5rem; display: block; }
}
</style>
