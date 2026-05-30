/**
 * 任務狀態管理
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Task } from '@/types/task'

import { getApiBase } from '@/composables/useApi'
import { createLogger } from '@/utils/logger'
import { adoptCompletedDownload } from '@/composables/videoDownloadComplete'

const log = createLogger('TaskStore')

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
      for (const taskData of data) {
        const existing = previousTasks.get(taskData.task_id)
        // Log status transitions
        if (existing && existing.status !== taskData.status) {
          log.info('task status changed', {
            taskId: taskData.task_id, taskType: taskData.task_type,
            from: existing.status, to: taskData.status,
          })
        }
        const task: Task = {
          taskId: taskData.task_id,
          taskType: taskData.task_type,
          status: taskData.status,
          progress: taskData.progress,
          message: taskData.message,
          result: taskData.result,
          error: taskData.error,
          createdAt: new Date(taskData.created_at),
          updatedAt: new Date(taskData.updated_at),
          label: existing?.label ?? taskData.label,
          fileName: existing?.fileName ?? taskData.file_name,
        }
        tasks.value.set(task.taskId, task)
        // Feature B: hand a freshly-completed video download to the Video tool.
        if (
          task.taskType === 'video.download' &&
          task.status === 'completed' &&
          existing?.status !== 'completed' &&
          task.result
        ) {
          adoptCompletedDownload(task.result as never)
        }
      }

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
    refreshTasks,
    startPolling,
    cleanup,
  }
})
