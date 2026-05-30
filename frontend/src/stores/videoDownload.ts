/**
 * 影片下載設定 store — 鏡像後端 DB-backed 設定;`enabled` 供 paste 守門同步檢查。
 * Fail-closed:load() 完成前一律 disabled。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiFetch } from '@/composables/useApi'

export type QualityMode = 'auto' | 'cap' | 'ask'

export interface VideoDownloadSettings {
  agreed: boolean
  enabled: boolean
  quality_mode: QualityMode
  max_height: number
}

const DEFAULTS: VideoDownloadSettings = {
  agreed: false,
  enabled: false,
  quality_mode: 'auto',
  max_height: 1080,
}

export const useVideoDownloadStore = defineStore('videoDownload', () => {
  const settings = ref<VideoDownloadSettings>({ ...DEFAULTS })
  const loaded = ref(false)

  const enabled = computed(() => settings.value.enabled)

  async function load(): Promise<void> {
    try {
      const res = await apiFetch('/video/download/settings')
      if (res.ok) settings.value = { ...DEFAULTS, ...(await res.json()) }
    } catch (e) {
      console.error('Failed to load video-download settings', e)
    } finally {
      loaded.value = true
    }
  }

  async function update(patch: Partial<VideoDownloadSettings>): Promise<void> {
    const res = await apiFetch('/video/download/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
    if (res.ok) settings.value = { ...DEFAULTS, ...(await res.json()) }
  }

  return { settings, loaded, enabled, load, update }
})
