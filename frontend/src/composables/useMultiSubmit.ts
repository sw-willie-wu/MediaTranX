import { computed } from 'vue'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useToast } from '@/composables/useToast'
import { createLogger } from '@/utils/logger'
import type { useMediaCollection } from '@/composables/useMediaCollection'

const log = createLogger('MultiSubmit')

export function useMultiSubmit(collection: ReturnType<typeof useMediaCollection>) {
  const toast = useToast()

  /**
   * True while any entry in the collection is being processed.
   */
  const isSubmitting = computed(() =>
    collection.entriesList.value.some((e) => e.status === 'processing'),
  )

  /**
   * Submit the same panel parameters to every selected entry concurrently.
   *
   * @param apiPath        API route, e.g. '/image/remove-bg'
   * @param getParams      Returns shared panel params WITHOUT file_id
   * @param label          Human-readable task label used in toasts
   * @param taskType       Machine-readable task type, e.g. 'image.remove_bg'
   * @param handlePanelSubmit  Workspace callback that registers the returned taskId
   */
  async function submitToAll(
    apiPath: string,
    getParams: () => Record<string, unknown>,
    label: string,
    taskType: string,
    handlePanelSubmit: (taskId: string) => void,
  ): Promise<void> {
    const selectedIds = Array.from(collection.selectedIds.value)

    // Resolve entries, skip any that are already processing
    const targets = selectedIds
      .map((id) => collection.entries.value.get(id))
      .filter(
        (entry): entry is NonNullable<typeof entry> =>
          entry !== undefined && entry.status !== 'processing' && entry.fileId !== null,
      )

    if (targets.length === 0) {
      log.warn('submitToAll: no eligible targets')
      toast.show('沒有可提交的項目', { type: 'info', icon: 'bi-info-circle' })
      return
    }

    log.info('submitToAll', { apiPath, taskType, targetCount: targets.length })
    const sharedParams = getParams()

    const FILTER_TYPE = 'image.filter'

    const results = await Promise.all(
      targets.map(async (entry) => {
        // For filter tasks, use the base (non-filter) file in history,
        // so repeated adjustments are non-destructive.
        let targetFileId = entry.fileId
        if (taskType === FILTER_TYPE) {
          const stack = entry.historyStack
          for (let i = stack.length - 1; i >= 0; i--) {
            if (stack[i].taskType !== FILTER_TYPE) {
              targetFileId = stack[i].fileId
              break
            }
          }
        } else {
          // Structural tasks operate on the latest result
          const latest = entry.historyStack.at(-1)
          if (latest) targetFileId = latest.fileId
        }

        const { submitTask } = useSubmitTask()
        const taskId = await submitTask(
          apiPath,
          { ...sharedParams, file_id: targetFileId },
          label,
          taskType,
          entry.file.name,
        )
        if (taskId) {
          // Register the task against this specific entry id, then mark it
          collection.registerTask(taskId, entry.id)
          collection.updateEntry(entry.id, { currentTaskId: taskId, status: 'processing' })
          handlePanelSubmit(taskId)
        }
        return taskId
      }),
    )

    const successCount = results.filter(Boolean).length
    log.info('submitToAll done', { successCount, totalCount: targets.length })

    if (successCount > 0) {
      toast.show(`已提交 ${successCount} 個任務`, { type: 'success', icon: 'bi-check-circle' })
    }
  }

  return {
    isSubmitting,
    submitToAll,
  }
}
