/**
 * API 客戶端 composable
 */
import { ref } from 'vue'

export function getApiBase() {
  // @ts-ignore
  const port = window.electron?.backendPort
  // 如果在 Electron 環境且有 port，使用絕對地址；否則在開發環境使用相對路徑 /api (由 Vite Proxy 處理)
  return port ? `http://localhost:${port}/api` : '/api'
}

/** 替換 fetch('/api/...') 的全局輔助函式 */
export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${getApiBase()}${path}`, init)
}

export interface UseApiOptions {
  immediate?: boolean
}

export function useApi<T>(
  endpoint: string,
  options: UseApiOptions = {}
) {
  const data = ref<T | null>(null)
  const error = ref<Error | null>(null)
  const isLoading = ref(false)

  async function execute(fetchOptions?: RequestInit): Promise<T | null> {
    isLoading.value = true
    error.value = null

    try {
      const response = await fetch(`${getApiBase()}${endpoint}`, {
        headers: {
          'Content-Type': 'application/json',
        },
        ...fetchOptions,
      })

      if (!response.ok) {
        throw new Error(`API error: ${response.status} ${response.statusText}`)
      }

      data.value = await response.json()
      return data.value
    } catch (err) {
      error.value = err instanceof Error ? err : new Error(String(err))
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function get(): Promise<T | null> {
    return execute({ method: 'GET' })
  }

  async function post(body: unknown): Promise<T | null> {
    return execute({
      method: 'POST',
      body: JSON.stringify(body),
    })
  }

  async function put(body: unknown): Promise<T | null> {
    return execute({
      method: 'PUT',
      body: JSON.stringify(body),
    })
  }

  async function del(): Promise<T | null> {
    return execute({ method: 'DELETE' })
  }

  // 立即執行
  if (options.immediate) {
    get()
  }

  return {
    data,
    error,
    isLoading,
    execute,
    get,
    post,
    put,
    delete: del,
  }
}

/**
 * 上傳檔案的專用函數
 */
export async function uploadFile(file: File): Promise<{
  file_id: string
  filename: string
  file_size: number
  mime_type: string
}> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${getApiBase()}/files/upload`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.statusText}`)
  }

  return response.json()
}

/**
 * 下載檔案
 */
export async function downloadFile(fileId: string, filename?: string): Promise<void> {
  const response = await fetch(`${getApiBase()}/files/${fileId}/download`)

  if (!response.ok) {
    throw new Error('Download failed')
  }

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)

  const a = document.createElement('a')
  a.href = url
  a.download = filename || 'download'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)

  URL.revokeObjectURL(url)
}
