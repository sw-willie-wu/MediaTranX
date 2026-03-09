/**
 * 任務狀態管理
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Task, ProgressUpdate } from '@/types/task'

import { getApiBase } from '@/composables/useApi'

export const useTaskStore = defineStore('tasks', () => {
  // 狀態
  const tasks = ref<Map<string, Task>>(new Map())
  const eventSources = ref<Map<string, EventSource>>(new Map())

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

    // 建立本地任務記錄
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

    // 訂閱進度更新
    subscribeToProgress(taskId)

    return taskId
  }

  // 註冊任務並自動訂閱 SSE
  function addTask(task: Task) {
    tasks.value.set(task.taskId, task)
    if (task.status === 'pending' || task.status === 'processing') {
      subscribeToProgress(task.taskId)
    }
  }

  // 訂閱 SSE 進度更新
  function subscribeToProgress(taskId: string) {
    // 如果已經有訂閱，先關閉
    const existingSource = eventSources.value.get(taskId)
    if (existingSource) {
      existingSource.close()
    }

    const eventSource = new EventSource(`${getApiBase()}/tasks/${taskId}/progress`)
    eventSources.value.set(taskId, eventSource)

    eventSource.onmessage = (event) => {
      const data: ProgressUpdate = JSON.parse(event.data)
      const task = tasks.value.get(taskId)

      if (task) {
        task.progress = data.progress
        task.message = data.message
        task.updatedAt = new Date()

        // 判斷狀態
        if (data.stage === 'completed') {
          task.status = 'completed'
          task.progress = 1.0
          if (data.result) task.result = data.result
          eventSource.close()
          eventSources.value.delete(taskId)
        } else if (data.stage === 'error') {
          task.status = 'failed'
          task.error = data.message
          eventSource.close()
          eventSources.value.delete(taskId)
        } else {
          task.status = 'processing'
        }
      }
    }

    eventSource.onerror = () => {
      eventSource.close()
      eventSources.value.delete(taskId)

      const task = tasks.value.get(taskId)
      if (task && task.status === 'processing') {
        task.status = 'failed'
        task.error = 'Connection lost'
      }
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
          task.status = 'cancelled'
          task.updatedAt = new Date()
        }

        // 關閉 SSE 連線
        const eventSource = eventSources.value.get(taskId)
        if (eventSource) {
          eventSource.close()
          eventSources.value.delete(taskId)
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

  // 重新載入任務列表
  async function refreshTasks(): Promise<void> {
    try {
      const response = await fetch(`${getApiBase()}/tasks`)
      const data = await response.json()

      const previousTasks = new Map(tasks.value)
      tasks.value.clear()
      for (const taskData of data) {
        const existing = previousTasks.get(taskData.task_id)
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

        // 對進行中的任務重新訂閱
        if (task.status === 'pending' || task.status === 'processing') {
          subscribeToProgress(task.taskId)
        }
      }
    } catch (error) {
      console.error('Failed to refresh tasks:', error)
    }
  }

  // 清理
  function cleanup() {
    for (const eventSource of eventSources.value.values()) {
      eventSource.close()
    }
    eventSources.value.clear()
  }

  return {
    // 狀態
    tasks,
    activeTasks,
    completedTasks,
    failedTasks,
    allTasks,
    activeCount,
    // 方法
    addTask,
    submitTask,
    cancelTask,
    removeTask,
    refreshTasks,
    subscribeToProgress,
    cleanup,
  }
})
