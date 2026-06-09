/**
 * 任務狀態管理
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Task } from '@/types/task'

import { getApiBase } from '@/composables/useApi'
import { createLogger } from '@/utils/logger'

const log = createLogger('TaskStore')

// Module-level dedup set: each unique notice (code + params) is toasted once per session.
const shownNotices = new Set<string>()

export const useTaskStore = defineStore('tasks', () => {
  // 狀態
  const tasks = ref<Map<string, Task>>(new Map())
  const pollingInterval = ref<ReturnType<typeof setInterval> | null>(null)

  // 計算屬性
  const activeTasks = computed(() =>
    Array.from(tasks.value.values()).filter(
      (t) => t.status === 'pending' || t.status === 'processing'
    )
  )

  const completedTasks = computed(() =>
    Array.from(tasks.value.values()).filter((t) => t.status === 'completed')
  )

  const failedTasks = computed(() =>
    Array.from(tasks.value.values()).filter((t) => t.status === 'failed')
  )

  const allTasks = computed(() => Array.from(tasks.value.values()))

  const activeCount = computed(() => activeTasks.value.length)

  function startPolling() {
    if (pollingInterval.value !== null) return
    pollingInterval.value = setInterval(refreshTasks, 1000)
  }

  function stopPolling() {
    if (pollingInterval.value !== null) {
      clearInterval(pollingInterval.value)
      pollingInterval.value = null
    }
  }

  // 提交任務
  async function submitTask(
    taskType: string,
    params: Record<string, unknown>
  ): Promise<string> {
    const response = await fetch(`${getApiBase()}/${taskType}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    })

    if (!response.ok) {
      throw new Error(`Failed to submit task: ${response.statusText}`)
    }

    const data = await response.json()
    const taskId = data.task_id

    const task: Task = {
      taskId,
      taskType,
      status: 'pending',
      progress: 0,
      message: 'Task submitted',
      result: null,
      error: null,
      createdAt: new Date(),
      updatedAt: new Date(),
    }
    tasks.value.set(taskId, task)
    startPolling()

    return taskId
  }

  // 註冊任務並啟動輪詢
  function addTask(task: Task) {
    log.info('addTask', { taskId: task.taskId, taskType: task.taskType, label: task.label })
    tasks.value.set(task.taskId, task)
    if (task.status === 'pending' || task.status === 'processing') {
      startPolling()
    }
  }

  // 取消任務
  async function cancelTask(taskId: string): Promise<boolean> {
    try {
      const response = await fetch(`${getApiBase()}/tasks/${taskId}/cancel`, {
        method: 'POST',
      })

      if (response.ok) {
        const task = tasks.value.get(taskId)
        if (task) {
          // pending 立即取消；processing 由 polling 同步真實狀態
          if (task.status === 'pending') {
            task.status = 'cancelled'
            task.updatedAt = new Date()
          } else {
            task.message = '取消中…'
          }
        }
        return true
      }
    } catch (error) {
      console.error('Failed to cancel task:', error)
    }
    return false
  }

  // 移除任務
  async function removeTask(taskId: string): Promise<boolean> {
    try {
      const response = await fetch(`${getApiBase()}/tasks/${taskId}`, {
        method: 'DELETE',
      })

      if (response.ok) {
        tasks.value.delete(taskId)
        return true
      }
    } catch (error) {
      console.error('Failed to remove task:', error)
    }
    return false
  }

  // 核心：將後端 task 資料陣列套用到 store（可被 refreshTasks 與測試直接呼叫）
  // previousSnapshot: 若由 refreshTasks 呼叫，傳入 clear 前的快照以正確偵測狀態轉換；
  //                   直接呼叫時省略，自動從目前 tasks 取快照。
  function applyTaskUpdates(
    data: Record<string, unknown>[],
    previousSnapshot?: Map<string, Task>,
  ): void {
    const previousTasks = previousSnapshot ?? new Map(tasks.value)
    for (const taskData of data) {
      const existing = previousTasks.get(taskData.task_id as string)
      // Log status transitions
      if (existing && existing.status !== taskData.status) {
        log.info('task status changed', {
          taskId: taskData.task_id, taskType: taskData.task_type,
          from: existing.status, to: taskData.status,
        })
      }
      const task: Task = {
        taskId: taskData.task_id as string,
        taskType: taskData.task_type as string,
        status: taskData.status as Task['status'],
        progress: taskData.progress as number,
        message: taskData.message as string | null,
        result: taskData.result as unknown,
        error: taskData.error as string | null,
        errorCode: (taskData.error_code as string | null | undefined) ?? null,
        notices: (taskData.notices as { code: string; params: Record<string, unknown> }[] | undefined) ?? [],
        createdAt: new Date(taskData.created_at as string),
        updatedAt: new Date(taskData.updated_at as string),
        label: existing?.label ?? (taskData.label as string | undefined),
        fileName: existing?.fileName ?? (taskData.file_name as string | undefined),
      }
      tasks.value.set(task.taskId, task)
      // Feature B: hand a freshly-completed video download to the Video tool.
      if (
        task.taskType === 'video.download' &&
        task.status === 'completed' &&
        existing?.status !== 'completed' &&
        task.result
      ) {
        // Lazy import: keeps @/i18n out of tasks.ts's static graph so node-env
        // test suites that import the store don't crash on module load.
        void import('@/composables/videoDownloadComplete').then((m) =>
          m.adoptCompletedDownload(task.result as never),
        )
      }
      // Notice dedup + toast: each unique notice (code + params) is shown once per session.
      for (const n of (taskData.notices as { code: string; params?: Record<string, unknown> }[] | undefined) ?? []) {
        const key = `${n.code}:${JSON.stringify(n.params ?? {})}`
        if (shownNotices.has(key)) continue
        shownNotices.add(key)
        void Promise.all([import('@/i18n'), import('@/composables/useToast')]).then(
          ([i18n, toast]) => {
            // @/i18n default export → use .default.global.t
            const msg = i18n.default.global.t(`compute.notice.${n.code}`, n.params ?? {})
            toast.useToast().show(msg, { type: 'warning' })
          },
        )
      }
    }
  }

  // 重新載入任務列表（輪詢核心）
  async function refreshTasks(): Promise<void> {
    try {
      const response = await fetch(`${getApiBase()}/tasks/`)
      const data = await response.json()

      const previousTasks = new Map(tasks.value)
      // Preserve frontend-only tasks (not from backend)
      const frontendTasks = new Map<string, Task>()
      for (const [id, t] of previousTasks) {
        if (id.startsWith('midi-export-')) frontendTasks.set(id, t)
      }
      tasks.value.clear()
      for (const [id, t] of frontendTasks) tasks.value.set(id, t)

      applyTaskUpdates(data as Record<string, unknown>[], previousTasks)

      // 沒有 active task 時停止輪詢
      if (activeTasks.value.length === 0) {
        stopPolling()
      }
    } catch (error) {
      console.error('Failed to refresh tasks:', error)
    }
  }

  // 清理
  function cleanup() {
    stopPolling()
  }

  return {
    tasks,
    activeTasks,
    completedTasks,
    failedTasks,
    allTasks,
    activeCount,
    addTask,
    submitTask,
    cancelTask,
    removeTask,
    applyTaskUpdates,
    refreshTasks,
    startPolling,
    cleanup,
  }
})
