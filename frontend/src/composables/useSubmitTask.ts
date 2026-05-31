import { ref } from 'vue'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { getApiBase } from '@/composables/useApi'
import { createLogger } from '@/utils/logger'
import type { Task } from '@/types/task'
import i18n from '@/i18n'

const log = createLogger('SubmitTask')
const { t } = i18n.global

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
    log.info('submit', { apiPath, taskType, fileName, params: body })
    try {
      const resp = await fetch(`${getApiBase()}${apiPath}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}))
        throw new Error(errData.detail || t('toast.submit_error'))
      }

      const { task_id: taskId } = await resp.json()
      log.info('submitted', { taskId, taskType, fileName })

      const task: Task = {
        taskId,
        taskType,
        status: 'pending',
        progress: 0,
        message: t('toast.task_submitted', { label }),
        result: null,
        error: null,
        createdAt: new Date(),
        updatedAt: new Date(),
        label,
        fileName,
      }
      taskStore.addTask(task)
      toast.show(t('toast.task_submitted', { label }), { type: 'success', icon: 'bi-check-circle' })
      return taskId
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      log.error('submit failed', { apiPath, taskType, error: msg })
      toast.show(msg || t('toast.submit_failed'), { type: 'error', icon: 'bi-x-circle' })
      return null
    } finally {
      isProcessing.value = false
    }
  }

  return { submitTask, isProcessing }
}
