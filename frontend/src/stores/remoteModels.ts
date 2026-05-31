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
import { useToast } from '@/composables/useToast'
import i18n from '@/i18n'

const ENABLED_MODELS_KEY = 'remote-enabled-models'

export interface RemoteConnection {
  id: number
  provider: string
  name: string
  endpoint: string
  /** Whether a key is stored server-side. The plaintext key is never sent to
   *  the client (it stays in the backend and is resolved by conn_id). */
  has_api_key?: boolean
  /** Last-4 masked hint like "…AbCd", "⚠ undecryptable", or null. */
  key_hint?: string | null
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
  // 每個連線的抓取失敗狀態(true = list-models 失敗;與「真的沒 model」區分)
  const connError = ref<Record<number, boolean>>({})

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

  async function fetchConnModels(conn: { id: number }) {
    connLoading.value[conn.id] = true
    try {
      // conn_id only — the backend resolves the api_key server-side. Passing
      // the key as a query param leaked it into uvicorn access logs.
      const res = await apiFetch(`/setup/remote/models?conn_id=${conn.id}`)
      if (res.ok) {
        const data = await res.json()
        const models = (data.models as RemoteModelInfo[]).sort((a, b) => a.name.localeCompare(b.name))
        connModels.value[conn.id] = models
        connError.value[conn.id] = false
      } else {
        delete connModels.value[conn.id]   // 不留 []，下次 fetchAll 會重抓
        connError.value[conn.id] = true
      }
    } catch {
      delete connModels.value[conn.id]
      connError.value[conn.id] = true
    } finally {
      connLoading.value[conn.id] = false
    }
  }

  function clearConnCache(connId: number) {
    delete connModels.value[connId]
  }

  /** Load connections + every enabled connection's models in one pass.
   * The single source of truth for both Settings page and the tool dropdowns.
   * Called automatically by every action that mutates connection state.
   *
   * @param opts.notifyOnError  When true (lazy/refresh paths), show a single
   *   aggregated warning toast for any connections that failed to list models.
   *   Mutation callers (add/update/delete/toggle) pass nothing → default false
   *   → no toast spam. */
  async function fetchAll({ notifyOnError = false }: { notifyOnError?: boolean } = {}) {
    try {
      const connRes = await apiFetch('/setup/remote/connections')
      if (!connRes.ok) return
      const { connections: conns } = await connRes.json()
      connections.value = conns

      // prune 已不存在連線的 connError
      const liveIds = new Set<number>(conns.map((c: RemoteConnection) => c.id))
      for (const key of Object.keys(connError.value)) {
        if (!liveIds.has(Number(key))) delete connError.value[Number(key)]
      }

      // 並行抓取啟用且未快取的連線(掛掉的連線不拖累其他;後端已用
      // asyncio.to_thread 解阻塞,這裡才真正並行)
      const toFetch = conns.filter((c: RemoteConnection) => c.enabled && !connModels.value[c.id])
      await Promise.all(toFetch.map((c: RemoteConnection) => fetchConnModels(c)))

      const all: RemoteModelOption[] = []
      for (const conn of conns) {
        if (!conn.enabled) continue
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

      // 聚合失敗 toast — 只在 lazy/refresh 路徑(notifyOnError),mutation 不跳
      if (notifyOnError) {
        const failed = conns.filter((c: RemoteConnection) => connError.value[c.id])
        if (failed.length) {
          const names = failed.map((c: RemoteConnection) => c.name || c.provider).join('、')
          useToast().show(
            i18n.global.t('settings.remote.fetch_failed', { count: failed.length, names }),
            { type: 'warning' },
          )
        }
      }
    } catch (e) {
      console.error('Failed to fetch remote models', e)
    }
  }

  // lazy 入口:命中快取直接 return;進行中則共用同一個 fetch(避免兩面板
  // 近乎同時 mount 各打一次)。失敗 toast 走 notifyOnError 路徑。
  let inFlight: Promise<void> | null = null
  async function ensureLoaded() {
    if (loaded.value) return
    if (inFlight) return inFlight
    inFlight = fetchAll({ notifyOnError: true }).finally(() => { inFlight = null })
    return inFlight
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
    // api_key is a write-only field: send a new key to change it, or omit it
    // (null/undefined) to keep the stored one. It is never read back.
    payload: { name?: string; endpoint?: string; api_key?: string | null; enabled?: boolean },
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

  /** Fetch the plaintext API key for a connection on demand.
   *  Returns the key string, or null on any error / undecryptable.
   *  The result is intentionally NOT stored in reactive state. */
  async function revealKey(id: number): Promise<string | null> {
    const res = await apiFetch(`/setup/remote/connections/${id}/key`, { method: 'POST' })
    if (!res.ok) return null
    const data = await res.json()
    return data.api_key ?? null
  }

  return {
    // state
    connections, connModels, connLoading, connError,
    allModels, loaded,
    enabledIds, enabledModels,
    // queries
    byCapability,
    // model-level opt-in
    toggleEnabled,
    // model cache
    fetchConnModels, clearConnCache,
    // canonical refresh
    fetchAll, ensureLoaded,
    // connection CRUD (single source of truth)
    addConnection, deleteConnection, updateConnection, toggleConnection,
    // on-demand key reveal (plaintext, transient, not persisted)
    revealKey,
  }
})
