/**
 * Ollama 推論設定 store — 鏡像後端 DB-backed 設定（num_ctx 上限）。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiFetch } from '@/composables/useApi'

export interface OllamaSettings {
  ollama_num_ctx_cap: number
}

const DEFAULTS: OllamaSettings = { ollama_num_ctx_cap: 8192 }

export const useOllamaSettingsStore = defineStore('ollamaSettings', () => {
  const settings = ref<OllamaSettings>({ ...DEFAULTS })
  const loaded = ref(false)

  async function load(): Promise<void> {
    try {
      const res = await apiFetch('/setup/config/ollama')
      if (res.ok) settings.value = { ...DEFAULTS, ...(await res.json()) }
    } catch (e) {
      console.error('Failed to load ollama settings', e)
    } finally {
      loaded.value = true
    }
  }

  async function update(patch: Partial<OllamaSettings>): Promise<void> {
    const res = await apiFetch('/setup/config/ollama', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
    if (res.ok) settings.value = { ...DEFAULTS, ...(await res.json()) }
  }

  return { settings, loaded, load, update }
})
