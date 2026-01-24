/**
 * SSE 進度追蹤 composable
 */
import { ref, onUnmounted } from 'vue'
import type { ProgressUpdate } from '@/types/task'

const API_BASE = '/api'

export interface UseProgressOptions {
  onComplete?: (taskId: string) => void
  onError?: (taskId: string, error: string) => void
  onProgress?: (taskId: string, progress: number, message: string) => void
}

export function useProgress(options: UseProgressOptions = {}) {
  const progress = ref(0)
  const message = ref('')
  const stage = ref('')
  const isConnected = ref(false)
  const error = ref<string | null>(null)

  let eventSource: EventSource | null = null

  /**
   * 訂閱任務進度
   */
  function subscribe(taskId: string): void {
    // 先關閉現有連線
    unsubscribe()

    eventSource = new EventSource(`${API_BASE}/tasks/${taskId}/progress`)
    isConnected.value = true
    error.value = null

    eventSource.onmessage = (event) => {
      const data: ProgressUpdate = JSON.parse(event.data)

      progress.value = data.progress
      message.value = data.message
      stage.value = data.stage

      // 回調
      options.onProgress?.(taskId, data.progress, data.message)

      // 完成或錯誤時關閉連線
      if (data.progress >= 1) {
        options.onComplete?.(taskId)
        unsubscribe()
      } else if (data.stage === 'error') {
        error.value = data.message
        options.onError?.(taskId, data.message)
        unsubscribe()
      }
    }

    eventSource.onerror = () => {
      error.value = 'Connection lost'
      options.onError?.(taskId, 'Connection lost')
      unsubscribe()
    }
  }

  /**
   * 取消訂閱
   */
  function unsubscribe(): void {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    isConnected.value = false
  }

  /**
   * 重設狀態
   */
  function reset(): void {
    progress.value = 0
    message.value = ''
    stage.value = ''
    error.value = null
  }

  // 組件卸載時自動清理
  onUnmounted(() => {
    unsubscribe()
  })

  return {
    progress,
    message,
    stage,
    isConnected,
    error,
    subscribe,
    unsubscribe,
    reset,
  }
}

/**
 * 多任務進度追蹤
 */
export function useMultiProgress() {
  const tasks = ref<Map<string, {
    progress: number
    message: string
    stage: string
  }>>(new Map())

  const eventSources = new Map<string, EventSource>()

  function subscribe(taskId: string): void {
    if (eventSources.has(taskId)) return

    const eventSource = new EventSource(`${API_BASE}/tasks/${taskId}/progress`)
    eventSources.set(taskId, eventSource)

    tasks.value.set(taskId, {
      progress: 0,
      message: '',
      stage: 'pending',
    })

    eventSource.onmessage = (event) => {
      const data: ProgressUpdate = JSON.parse(event.data)
      tasks.value.set(taskId, {
        progress: data.progress,
        message: data.message,
        stage: data.stage,
      })

      if (data.progress >= 1 || data.stage === 'error') {
        eventSource.close()
        eventSources.delete(taskId)
      }
    }

    eventSource.onerror = () => {
      eventSource.close()
      eventSources.delete(taskId)
    }
  }

  function unsubscribe(taskId: string): void {
    const eventSource = eventSources.get(taskId)
    if (eventSource) {
      eventSource.close()
      eventSources.delete(taskId)
    }
  }

  function unsubscribeAll(): void {
    for (const [taskId] of eventSources) {
      unsubscribe(taskId)
    }
  }

  function remove(taskId: string): void {
    unsubscribe(taskId)
    tasks.value.delete(taskId)
  }

  onUnmounted(() => {
    unsubscribeAll()
  })

  return {
    tasks,
    subscribe,
    unsubscribe,
    unsubscribeAll,
    remove,
  }
}
