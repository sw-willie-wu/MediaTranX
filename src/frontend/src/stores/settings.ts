/**
 * 設定狀態管理
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { DeviceInfo } from '@/types/api'

import { apiFetch } from '@/composables/useApi'

export const useSettingsStore = defineStore('settings', () => {
  // 狀態
  const deviceInfo = ref<DeviceInfo | null>(null)
  const isLoading = ref(false)

  // 計算屬性
  const hasGPU = computed(() => deviceInfo.value?.device === 'cuda')
  const hasMPS = computed(() => deviceInfo.value?.device === 'mps')
  const isCPUOnly = computed(() => deviceInfo.value?.device === 'cpu')
  const needsCudaToolkit = computed(() =>
    deviceInfo.value?.has_nvidia_gpu === true && !deviceInfo.value?.cuda_toolkit_installed
  )

  const deviceDisplayName = computed(() => {
    if (!deviceInfo.value) return 'Unknown'
    if (hasGPU.value) return `GPU: ${deviceInfo.value.device_name}`
    if (hasMPS.value) return 'Apple Silicon'
    return 'CPU'
  })

  // 載入裝置資訊
  async function loadDeviceInfo(): Promise<void> {
    isLoading.value = true
    try {
      const response = await apiFetch('/device')
      if (response.ok) {
        deviceInfo.value = await response.json()
      }
    } catch (error) {
      console.error('Failed to load device info:', error)
    } finally {
      isLoading.value = false
    }
  }

  return {
    // 狀態
    deviceInfo,
    isLoading,
    hasGPU,
    hasMPS,
    isCPUOnly,
    needsCudaToolkit,
    deviceDisplayName,
    // 方法
    loadDeviceInfo,
  }
})
