/**
 * Remote Models Store
 *
 * 管理遠端 API 的模型列表和啟用狀態。
 * - connModels: 每個連線的模型快取（設定頁展開用）
 * - enabledModels: 啟用的模型（各工具 AppSelect 用）
 * - byCapability: 按能力篩選啟用的模型
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiFetch } from '@/composables/useApi'

const ENABLED_MODELS_KEY = 'remote-enabled-models'

export interface RemoteModelInfo {
  id: string
  name: string
  parameter_size?: string
  capabilities?: string[]
}

export interface RemoteModelOption {
  provider: string      // ollama, openai, ...
  connId: number
  endpoint: string
  modelId: string       // e.g. "llama3.2:3b"
  name: string
  parameterSize?: string
  capabilities: string[]
}

export const useRemoteModelStore = defineStore('remoteModels', () => {
  // 每個連線的模型快取（connId → models）
  const connModels = ref<Record<number, RemoteModelInfo[]>>({})
  const connLoading = ref<Record<number, boolean>>({})

  // 所有連線的模型彙總（啟用的連線）
  const allModels = ref<RemoteModelOption[]>([])
  const loaded = ref(false)

  // 啟用的模型 ID set
  const enabledIds = ref<Set<string>>(new Set(
    JSON.parse(localStorage.getItem(ENABLED_MODELS_KEY) || '[]')
  ))

  const enabledModels = computed(() =>
    allModels.value.filter(m => enabledIds.value.has(`${m.provider}:${m.modelId}`))
  )

  function byCapability(cap: string) {
    return enabledModels.value.filter(m => m.capabilities.includes(cap))
  }

  function toggleEnabled(key: string) {
    const next = new Set(enabledIds.value)
    if (next.has(key)) {
      next.delete(key)
    } else {
      next.add(key)
    }
    enabledIds.value = next
    localStorage.setItem(ENABLED_MODELS_KEY, JSON.stringify([...next]))
  }

  async function fetchConnModels(conn: { id: number; provider: string; endpoint: string; api_key?: string }) {
    connLoading.value[conn.id] = true
    try {
      const res = await apiFetch(
        `/setup/remote/models?provider=${conn.provider}&endpoint=${encodeURIComponent(conn.endpoint)}${conn.api_key ? `&api_key=${encodeURIComponent(conn.api_key)}` : ''}`
      )
      if (res.ok) {
        const data = await res.json()
        const models = (data.models as RemoteModelInfo[]).sort((a, b) => a.name.localeCompare(b.name))
        connModels.value[conn.id] = models
      } else {
        connModels.value[conn.id] = []
      }
    } catch {
      connModels.value[conn.id] = []
    } finally {
      connLoading.value[conn.id] = false
    }
  }

  function clearConnCache(connId: number) {
    delete connModels.value[connId]
  }

  async function fetchAll() {
    try {
      const connRes = await apiFetch('/setup/remote/connections')
      if (!connRes.ok) return
      const { connections } = await connRes.json()

      const all: RemoteModelOption[] = []
      for (const conn of connections) {
        if (!conn.enabled) continue
        // 用快取或重新 fetch
        if (!connModels.value[conn.id]) {
          await fetchConnModels(conn)
        }
        const models = connModels.value[conn.id] || []
        for (const m of models) {
          all.push({
            provider: conn.provider,
            connId: conn.id,
            endpoint: conn.endpoint,
            modelId: m.id,
            name: m.name,
            parameterSize: m.parameter_size,
            capabilities: m.capabilities || ['text'],
          })
        }
      }
      allModels.value = all
      loaded.value = true
    } catch (e) {
      console.error('Failed to fetch remote models', e)
    }
  }

  return {
    connModels, connLoading,
    allModels, loaded,
    enabledIds, enabledModels,
    byCapability, toggleEnabled,
    fetchConnModels, clearConnCache, fetchAll,
  }
})
