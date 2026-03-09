<script setup lang="ts">
import { onMounted } from 'vue'
import { useSettingsStore } from '@/stores/settings'

const settingsStore = useSettingsStore()

onMounted(() => {
  if (!settingsStore.deviceInfo) settingsStore.loadDeviceInfo()
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
  <h6 class="section-title">系統資訊</h6>

  <div v-if="settingsStore.isLoading" class="gpu-detecting">
    <div class="spinner"></div>
    <span>偵測硬體中...</span>
  </div>

  <template v-else-if="settingsStore.deviceInfo">
    <div class="sys-card">
      <i class="bi bi-window"></i>
      <span class="sys-name">作業系統</span>
      <span class="sys-detail">{{ settingsStore.deviceInfo.os_name }}</span>
    </div>

    <div class="sys-card">
      <i class="bi bi-cpu"></i>
      <span class="sys-name">處理器</span>
      <span class="sys-detail">
        {{ settingsStore.deviceInfo.cpu_name
        }}<template v-if="settingsStore.deviceInfo.cpu_count"
        > ({{ settingsStore.deviceInfo.cpu_count }} 執行緒)</template>
      </span>
    </div>

    <div class="sys-card">
      <i class="bi bi-memory"></i>
      <span class="sys-name">記憶體</span>
      <span class="sys-detail">{{ formatRam(settingsStore.deviceInfo.ram_total) }}</span>
    </div>

    <div class="sys-card">
      <i class="bi bi-gpu-card"></i>
      <span class="sys-name">顯示卡</span>
      <span v-if="settingsStore.deviceInfo.has_nvidia_gpu" class="sys-detail">
        {{ settingsStore.deviceInfo.device_name
        }}<template v-if="settingsStore.deviceInfo.memory_total"
        > · {{ formatVram(settingsStore.deviceInfo.memory_total) }}</template
        ><template v-if="settingsStore.deviceInfo.driver_version"
        > · 驅動 {{ settingsStore.deviceInfo.driver_version }}</template>
      </span>
      <span v-else class="sys-detail sys-muted">未偵測到 GPU</span>
    </div>
  </template>

  <div v-else class="sys-error-state">
    <i class="bi bi-exclamation-circle"></i>
    <p>無法讀取硬體狀態</p>
    <button class="retry-btn" @click="settingsStore.loadDeviceInfo()">重新偵測</button>
  </div>

  <button
    v-if="!settingsStore.isLoading"
    class="refresh-btn"
    @click="settingsStore.loadDeviceInfo()"
    :disabled="settingsStore.isLoading"
  >
    <i class="bi bi-arrow-clockwise" :class="{ spin: settingsStore.isLoading }"></i> 重新整理
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
  width: 72px;
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

.retry-btn {
  padding: 0.6rem 2rem;
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  &:hover { opacity: 0.9; }
}

.refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 1rem;
  padding: 0.4rem 0.875rem;
  background: transparent;
  border: 1px solid var(--input-border);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s ease;
  &:hover { background: var(--panel-bg-hover); color: var(--text-primary); }
  &:disabled { opacity: 0.5; cursor: not-allowed; }

  i.spin { animation: settings-spin 1s linear infinite; }
}
</style>
