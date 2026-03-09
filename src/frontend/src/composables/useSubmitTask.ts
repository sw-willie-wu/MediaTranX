import { ref } from 'vue'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { getApiBase } from '@/composables/useApi'
import type { Task } from '@/types/task'

export function useSubmitTask() {
  const taskStore = useTaskStore()
  const toast = useToast()
  const isProcessing = ref(false)

  async function submitTask(
    apiPath: string,
    body: Record<string, unknown>,
    label: string,
    taskType: string,
    fileName: string = '',
  ): Promise<string | null> {
    isProcessing.value = true
    try {
      const resp = await fetch(`${getApiBase()}${apiPath}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}))
        throw new Error(errData.detail || '提交任務失敗')
      }

      const { task_id: taskId } = await resp.json()

      const task: Task = {
        taskId,
        taskType,
        status: 'pending',
        progress: 0,
        message: '任務已提交',
        result: null,
        error: null,
        createdAt: new Date(),
        updatedAt: new Date(),
        label,
        fileName,
      }
      taskStore.addTask(task)
      toast.show(`${label}任務已提交`, { type: 'success', icon: 'bi-check-circle' })
      return taskId
    } catch (e: any) {
      toast.show(e.message || '提交失敗', { type: 'error', icon: 'bi-x-circle' })
      return null
    } finally {
      isProcessing.value = false
    }
  }

  return { submitTask, isProcessing }
}
