import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiFetch } from '@/composables/useApi'

export interface ModelItem {
  id: string
  label: string
  category: string
  downloaded: boolean
  size_mb: number
  family: string
  variant: string
  description?: string
  vram_mb?: number
  max_scale?: number
}

export interface ModelCategory {
  key: string
  label: string
  order: number
}

export const useModelStore = defineStore('models', () => {
  const models = ref<ModelItem[]>([])
  const categories = ref<ModelCategory[]>([])
  const loading = ref(false)
  const loaded = ref(false)

  async function fetchModels() {
    loading.value = true
    try {
      const res = await apiFetch('/setup/models')
      if (res.ok) {
        const data = await res.json()
        models.value = data.models as ModelItem[]
        categories.value = (data.categories as ModelCategory[]).sort((a, b) => a.order - b.order)
        loaded.value = true
      }
    } catch (e) {
      console.error('Failed to load models', e)
    } finally {
      loading.value = false
    }
  }

  /** 確保至少載入過一次；若已載入則直接返回 */
  async function ensureLoaded() {
    if (!loaded.value && !loading.value) await fetchModels()
  }

  function setDownloaded(id: string, downloaded: boolean) {
    const m = models.value.find(m => m.id === id)
    if (m) m.downloaded = downloaded
  }

  function byCategory(category: string): ModelItem[] {
    return models.value.filter(m => m.category === category)
  }

  return { models, categories, loading, loaded, fetchModels, ensureLoaded, setDownloaded, byCategory }
})
