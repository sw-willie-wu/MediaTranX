import { ref, computed, type ComputedRef } from 'vue'
import { useTaskStore } from '@/stores/tasks'
import { useConfirm } from '@/composables/useConfirm'
import { useToast } from '@/composables/useToast'
import { createLogger } from '@/utils/logger'
import i18n from '@/i18n'
import type { useMediaCollection } from '@/composables/useMediaCollection'

const log = createLogger('ExecuteStop')
const { t } = i18n.global

/**
 * 工具頁「執行→停止」共用邏輯（spec: .claude/specs/execute-stop-button.md §4.2）。
 * 停全部：取消該頁 collection 中所有 in-flight 任務。
 * cancelingIds 每輪整組覆蓋——canceling 期間按鈕 disabled、同時只有一輪，
 * 覆蓋即天然清掉舊 id；reactivity 主承載是 ref 重新賦值。
 */
export function useExecuteStop(
  collection: Pick<ReturnType<typeof useMediaCollection>, 'entriesList'>,
): { isCanceling: ComputedRef<boolean>; requestStop: () => Promise<void> } {
  const taskStore = useTaskStore()
  const { confirm } = useConfirm()
  const toast = useToast()

  const cancelingIds = ref(new Set<string>())

  const isCanceling = computed(() =>
    collection.entriesList.value.some(
      e => e.status === 'processing' && e.currentTaskId !== null && cancelingIds.value.has(e.currentTaskId),
    ),
  )

  function enumerateInFlight(): string[] {
    return collection.entriesList.value
      .filter(e => e.status === 'processing' && e.currentTaskId !== null)
      .map(e => e.currentTaskId as string)
  }

  async function requestStop(): Promise<void> {
    const count = enumerateInFlight().length
    const ok = await confirm({
      type: 'danger',
      title: t('common.stop_confirm_title'),
      message: t('common.stop_confirm_message', { count }),
      confirmLabel: t('common.stop'),
      cancelLabel: t('common.cancel'),
    })
    if (!ok) return

    // 確認後才枚舉：涵蓋提交窗口與對話框停留期間的變動（spec §4.2 步驟 3）
    const targets = enumerateInFlight()
    if (targets.length === 0) {
      cancelingIds.value = new Set()
      return
    }
    log.info('requestStop', { count: targets.length })
    cancelingIds.value = new Set(targets)
    const results = await Promise.all(targets.map(id => taskStore.cancelTask(id)))
    let failed = 0
    results.forEach((success, i) => {
      if (!success) {
        cancelingIds.value.delete(targets[i])
        failed++
      }
    })
    if (failed > 0) {
      log.warn('cancel failed', { failed })
      toast.show(t('toast.cancel_failed'), { type: 'error', icon: 'bi-x-circle' })
    }
  }

  return { isCanceling, requestStop }
}
