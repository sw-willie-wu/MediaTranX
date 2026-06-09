/**
 * 計算政策設定 store — 鏡像後端 DB-backed 設定（GPU→CPU 自動降級開關）。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiFetch } from '@/composables/useApi'

export interface ComputeSettings {
  allow_cpu_fallback: boolean
}

const DEFAULTS: ComputeSettings = { allow_cpu_fallback: true }

export const useComputeSettingsStore = defineStore('computeSettings', () => {
  const settings = ref<ComputeSettings>({ ...DEFAULTS })
  const loaded = ref(false)

  async function load(): Promise<void> {
    try {
      const res = await apiFetch('/setup/config/compute')
      if (res.ok) settings.value = { ...DEFAULTS, ...(await res.json()) }
    } catch (e) {
      console.error('Failed to load compute settings', e)
    } finally {
      loaded.value = true
    }
  }

  async function update(patch: Partial<ComputeSettings>): Promise<void> {
    const res = await apiFetch('/setup/config/compute', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
    if (res.ok) settings.value = { ...DEFAULTS, ...(await res.json()) }
  }

  return { settings, loaded, load, update }
})
