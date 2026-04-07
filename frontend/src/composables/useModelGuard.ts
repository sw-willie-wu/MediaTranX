/**
 * useModelGuard
 *
 * 執行前檢查模型是否已下載，未下載則彈出確認框導向模型管理頁面。
 */
import { useConfirm } from '@/composables/useConfirm'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

export function useModelGuard() {
  const { confirm } = useConfirm()
  const router = useRouter()
  const { t } = useI18n()

  /**
   * 檢查模型是否已下載。
   * @param isDownloaded - 模型是否已下載
   * @param category - 模型分類 tab（'image' | 'audio' | 'video' | 'llm'），用於導航
   * @returns true = 已下載可繼續執行；false = 未下載已攔截
   */
  async function guardModelReady(isDownloaded: boolean, category?: string): Promise<boolean> {
    if (isDownloaded) return true

    const ok = await confirm({
      title: t('common.model_not_ready'),
      message: t('common.model_not_downloaded_hint'),
      confirmLabel: t('common.go_to_model_manager'),
      type: 'warning',
    })

    if (ok) {
      const query: Record<string, string> = { tab: 'models' }
      if (category) query.category = category
      router.push({ path: '/settings', query })
    }
    return false
  }

  return { guardModelReady }
}
