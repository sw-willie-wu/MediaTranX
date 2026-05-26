/**
 * Remote Models Store
 *
 * 管理遠端 API 連線 + 模型列表，是所有遠端模型狀態的 single source of truth。
 * - connections: 連線列表（取代 ModelDownloadManager 內部 ref）
 * - connModels: 每個連線的模型快取（設定頁展開用）
 * - allModels:  所有啟用連線的模型彙總
 * - enabledModels / byCapability: 工具下拉用，加上 per-model opt-in 過濾
 *
 * 設計原則：
 * - 任何會改動 server 連線狀態的動作（add / update / delete / toggle）
 *   都走本 store 的 action method、結尾自動 fetchAll() 同步全域狀態
 * - 元件只 read + dispatch action、不再自己 keep 一份 connections ref
 * - fetchAll() 同時填 connections 跟 allModels，避免雙 fetch
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiFetch } from '@/composables/useApi'

const ENABLED_MODELS_KEY = 'remote-enabled-models'

export interface RemoteConnection {
  id: number
  provider: string
  name: string
  endpoint: string
  api_key?: string
  enabled: boolean
}

export interface RemoteModelInfo {
  id: string
  name: string
  parameter_size?: string
  capabilities?: string[]
}

export interface RemoteModelOption {
  provider: string      // ollama, openai, ...
  connId: number
  connName: string      // 使用者自訂的連線名稱
  endpoint: string
  modelId: string       // e.g. "llama3.2:3b"
  name: string
  parameterSize?: string
  capabilities: string[]
}

export const useRemoteModelStore = defineStore('remoteModels', () => {
  // 連線列表（取代之前在 ModelDownloadManager 內的 local ref）
  const connections = ref<RemoteConnection[]>([])

  // 每個連線的模型快取（connId → models）
  const connModels = ref<Record<number, RemoteModelInfo[]>>({})
  const connLoading = ref<Record<number, boolean>>({})

  // 所有連線的模型彙總（啟用的連線）
  const allModels = ref<RemoteModelOption[]>([])
  const loaded = ref(false)

  // 啟用的模型 ID set（per-model opt-in，存 localStorage）
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

  /** Load connections + every enabled connection's models in one pass.
   * The single source of truth for both Settings page and the tool dropdowns.
   * Called automatically by every action that mutates connection state. */
  async function fetchAll() {
    try {
      const connRes = await apiFetch('/setup/remote/connections')
      if (!connRes.ok) return
      const { connections: conns } = await connRes.json()
      connections.value = conns

      const all: RemoteModelOption[] = []
      for (const conn of conns) {
        if (!conn.enabled) continue
        if (!connModels.value[conn.id]) {
          await fetchConnModels(conn)
        }
        const models = connModels.value[conn.id] || []
        for (const m of models) {
          all.push({
            provider: conn.provider,
            connId: conn.id,
            connName: conn.name || conn.provider,
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

  // ─── Connection CRUD actions ─────────────────────────────────
  // All mutations end by calling fetchAll() so connections + allModels
  // refresh together. Consumers of byCapability/enabledModels see the
  // change immediately via Pinia reactivity.

  async function addConnection(payload: {
    provider: string; name: string; endpoint: string; api_key?: string
  }): Promise<boolean> {
    const res = await apiFetch('/setup/remote/connections', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) return false
    await fetchAll()
    return true
  }

  async function deleteConnection(id: number): Promise<boolean> {
    const res = await apiFetch(`/setup/remote/connections/${id}`, { method: 'DELETE' })
    if (!res.ok) return false
    clearConnCache(id)
    await fetchAll()
    return true
  }

  async function updateConnection(
    id: number,
    payload: Partial<Pick<RemoteConnection, 'name' | 'endpoint' | 'api_key' | 'enabled'>>,
  ): Promise<boolean> {
    const res = await apiFetch(`/setup/remote/connections/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) return false
    // If endpoint or api_key may have changed, the cached model list for this
    // conn is stale (different Ollama instance / different OpenAI key →
    // different model set). Drop cache so fetchAll re-queries.
    if ('endpoint' in payload || 'api_key' in payload) {
      clearConnCache(id)
    }
    await fetchAll()
    return true
  }

  async function toggleConnection(id: number, enabled: boolean): Promise<boolean> {
    return updateConnection(id, { enabled })
  }

  return {
    // state
    connections, connModels, connLoading,
    allModels, loaded,
    enabledIds, enabledModels,
    // queries
    byCapability,
    // model-level opt-in
    toggleEnabled,
    // model cache
    fetchConnModels, clearConnCache,
    // canonical refresh
    fetchAll,
    // connection CRUD (single source of truth)
    addConnection, deleteConnection, updateConnection, toggleConnection,
  }
})
