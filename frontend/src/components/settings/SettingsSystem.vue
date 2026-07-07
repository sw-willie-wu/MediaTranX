<script setup lang="ts">
import { onMounted } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'
import { useComputeSettingsStore } from '@/stores/computeSettings'
import AppToggle from '@/components/common/AppToggle.vue'

const settingsStore = useSettingsStore()
const computeStore = useComputeSettingsStore()

onMounted(() => {
  if (!settingsStore.deviceInfo) settingsStore.loadDeviceInfo()
  if (!computeStore.loaded) computeStore.load()
})

useAgentPanelHost('settings.system', {
  agentSchema: {
    panelId: 'settings.system',
    fields: [],
    actions: [
      { name: 'restart_backend', label: 'Restart Backend' },
      { name: 'browse_data_dir', label: 'Browse Data Directory' },
    ],
    execute: null,
  },
  getCurrentValues: () => ({}),
  setField: (_field: string, _value: unknown) => {
    throw new Error('agent.error.no_execute_on_settings')
  },
  openField: (_field: string) => {},
  execute: () => { throw new Error('agent.error.no_execute_on_settings') },
  invokeAction: (name: string) => {
    if (name === 'restart_backend') {
      window.electron?.restart()
      return { ok: true }
    }
    // browse_data_dir: not implemented in this panel
    return null
  },
  isMultiSelect: () => false,
})

function formatVram(bytes: number | null): string {
  if (!bytes) return ''
  const gb = bytes / (1024 * 1024 * 1024)
  return `${gb.toFixed(1)} GB`
}

function formatRam(bytes: number | null): string {
  if (!bytes) return 'N/A'
  const gb = bytes / (1024 * 1024 * 1024)
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / (1024 * 1024)).toFixed(0)} MB`
}
</script>

<template>
  <h6 class="section-title">{{ $t('settings.system.info') }}</h6>

  <div v-if="settingsStore.isLoading" class="gpu-detecting">
    <div class="spinner"></div>
    <span>{{ $t('settings.system.detecting') }}</span>
  </div>

  <template v-else-if="settingsStore.deviceInfo">
    <div class="sys-card">
      <i class="bi bi-window"></i>
      <span class="sys-name">{{ $t('settings.system.os') }}</span>
      <span class="sys-detail">{{ settingsStore.deviceInfo.os_name }}</span>
    </div>

    <div class="sys-card">
      <i class="bi bi-cpu"></i>
      <span class="sys-name">{{ $t('settings.system.cpu') }}</span>
      <span class="sys-detail">
        {{ settingsStore.deviceInfo.cpu_name
        }}<template v-if="settingsStore.deviceInfo.cpu_count"
        > ({{ settingsStore.deviceInfo.cpu_count }} {{ $t('settings.system.threads') }})</template>
      </span>
    </div>

    <div class="sys-card">
      <i class="bi bi-memory"></i>
      <span class="sys-name">{{ $t('settings.system.memory') }}</span>
      <span class="sys-detail">{{ formatRam(settingsStore.deviceInfo.ram_total) }}</span>
    </div>

    <div class="sys-card">
      <i class="bi bi-gpu-card"></i>
      <span class="sys-name">{{ $t('settings.system.gpu') }}</span>
      <span v-if="settingsStore.deviceInfo.has_nvidia_gpu" class="sys-detail">
        {{ settingsStore.deviceInfo.device_name
        }}<template v-if="settingsStore.deviceInfo.memory_total"
        > · {{ formatVram(settingsStore.deviceInfo.memory_total) }}</template
        ><template v-if="settingsStore.deviceInfo.driver_version"
        > · {{ $t('settings.system.driver') }} {{ settingsStore.deviceInfo.driver_version }}</template>
      </span>
      <span v-else class="sys-detail sys-muted">{{ $t('settings.system.no_gpu') }}</span>
    </div>
  </template>

  <div v-else class="sys-error-state">
    <i class="bi bi-exclamation-circle"></i>
    <p>{{ $t('settings.system.error') }}</p>
    <button class="btn-primary" @click="settingsStore.loadDeviceInfo()">{{ $t('settings.system.redetect') }}</button>
  </div>

  <h6 class="section-title mt">{{ $t('settings.system.compute_policy') }}</h6>

  <div class="setting-item">
    <AppToggle
      :model-value="computeStore.settings.allow_cpu_fallback"
      @update:model-value="(v) => computeStore.update({ allow_cpu_fallback: v })"
    >
      {{ $t('settings.system.cpu_fallback') }}
    </AppToggle>
    <p class="setting-hint">{{ $t('settings.system.cpu_fallback_hint') }}</p>
  </div>

  <div class="setting-item">
    <label class="concurrency-row">
      <span>{{ $t('settings.system.max_concurrent_tasks') }}</span>
      <select
        class="concurrency-select"
        :value="computeStore.settings.max_concurrent_tasks"
        @change="(e) => computeStore.update({ max_concurrent_tasks: Number((e.target as HTMLSelectElement).value) })"
      >
        <option v-for="n in 8" :key="n" :value="n">{{ n }}</option>
      </select>
    </label>
    <p class="setting-hint">{{ $t('settings.system.max_concurrent_tasks_hint') }}</p>
  </div>

  <p
    v-if="settingsStore.deviceInfo?.fallback_active"
    class="fallback-notice"
  >
    {{ $t(`compute.notice.${settingsStore.deviceInfo.fallback_reason}`) }}
  </p>

  <button
    v-if="!settingsStore.isLoading"
    class="btn-secondary refresh-btn"
    @click="settingsStore.loadDeviceInfo()"
    :disabled="settingsStore.isLoading"
  >
    <i class="bi bi-arrow-clockwise" :class="{ spin: settingsStore.isLoading }"></i> {{ $t('settings.system.refresh') }}
  </button>
</template>

<style lang="scss">
@use '@/styles/settings-shared';
</style>

<style lang="scss" scoped>
.gpu-detecting {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  background: var(--input-bg);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.sys-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.375rem 0.875rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 8px;
  margin-bottom: 1rem;

  > i {
    font-size: 0.95rem;
    color: var(--text-secondary);
    flex-shrink: 0;
    width: 18px;
    text-align: center;
  }
}

.sys-name {
  font-size: 0.875rem;
  color: var(--text-muted);
  flex-shrink: 0;
  white-space: nowrap;
}

.sys-detail {
  flex: 1;
  font-size: 0.875rem;
  color: var(--text-primary);
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  &.sys-muted { color: var(--text-muted); }
}

.sys-error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  text-align: center;
  color: var(--text-muted);
  i { font-size: 3rem; margin-bottom: 1rem; opacity: 0.5; }
  p { margin-bottom: 1.5rem; }
}

.refresh-btn {
  margin-top: 1rem;
  i.spin { animation: settings-spin 1s linear infinite; }
}

.setting-hint {
  color: var(--text-muted);
  font-size: 0.8rem;
  margin-top: 0.375rem;
  line-height: 1.4;
}

.concurrency-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  color: var(--text-primary);
  font-size: 0.9rem;
}

.concurrency-select {
  padding: 0.25rem 0.5rem;
  background: var(--input-bg);
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  color: var(--text-primary);
  font-family: inherit;
  font-size: 0.85rem;
}

.fallback-notice {
  color: var(--color-warning, #d97706);
  font-size: 0.85rem;
  margin-top: 0.5rem;
}
</style>
