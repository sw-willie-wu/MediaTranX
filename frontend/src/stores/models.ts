import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiFetch } from '@/composables/useApi'
import { useSettingsStore } from '@/stores/settings'

export interface ModelItem {
  id: string
  label: string
  category: string
  subcategory?: string
  capabilities?: string[]
  downloaded: boolean
  size_mb: number
  family: string
  variant: string
  description?: string
  vram_mb?: number
  max_scale?: number
  n_ctx_default?: number
  n_ctx_min?: number
  n_ctx_max?: number
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
  const version = ref(0)

  async function fetchModels() {
    loading.value = true
    try {
      const res = await apiFetch('/setup/models')
      if (res.ok) {
        const data = await res.json()
        models.value = data.models as ModelItem[]
        categories.value = (data.categories as ModelCategory[]).sort((a, b) => a.order - b.order)
        loaded.value = true
        version.value++
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
    version.value++
  }

  function byCategory(category: string): ModelItem[] {
    return models.value.filter(m => m.category === category || m.subcategory === category)
  }

  function byCapability(cap: string): ModelItem[] {
    return models.value.filter(m => m.capabilities?.includes(cap))
  }

  /** 為工具面板過濾：根據設定決定是否隱藏未下載模型 */
  function forPanel(items: ModelItem[]): ModelItem[] {
    const settings = useSettingsStore()
    if (settings.showAllModels) return items
    return items.filter(m => m.downloaded)
  }

  return { models, categories, loading, loaded, version, fetchModels, ensureLoaded, setDownloaded, byCategory, byCapability, forPanel }
})
