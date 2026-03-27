/**
 * 下載後端產出檔案到本機
 * 透過 Electron saveFileDialog 讓用戶選擇儲存路徑，再由 IPC 寫入磁碟
 */
import { useToast } from './useToast'
import { getApiBase } from './useApi'
import { createLogger } from '@/utils/logger'
import i18n from '@/i18n'

const toast = useToast()
const log = createLogger('FileDownload')
const { t } = i18n.global

export function useFileDownload() {
  async function downloadFile(fileId: string, defaultName: string, defaultDir?: string) {
    if (!window.electron?.saveFileDialog) return

    const ext = defaultName.split('.').pop() ?? ''
    const filters = ext
      ? [{ name: ext.toUpperCase(), extensions: [ext] }, { name: t('common.all_files'), extensions: ['*'] }]
      : [{ name: t('common.all_files'), extensions: ['*'] }]

    // 組合預設儲存路徑：若有原始目錄則用，否則只帶檔名讓系統決定位置
    const defaultPath = defaultDir
      ? `${defaultDir.replace(/\\/g, '/')}/${defaultName}`
      : defaultName

    const destPath = await window.electron.saveFileDialog({
      title: t('common.save'),
      defaultPath,
      filters,
    })
    if (!destPath) return

    log.info('downloadFile', { fileId, destPath })
    try {
      await window.electron.downloadToPath(
        `${getApiBase()}/files/${fileId}/download`,
        destPath,
      )
      log.info('downloadFile done', { fileId, destPath })
      toast.show(t('toast.saved'), {
        type: 'success',
        icon: 'bi-check-circle',
        action: window.electron?.showItemInFolder
          ? { label: t('toast.open_folder'), callback: () => window.electron!.showItemInFolder(destPath) }
          : undefined,
      })
    } catch (e) {
      log.error('downloadFile failed', { fileId, destPath, error: e })
      toast.show(t('toast.save_failed'), { type: 'error', icon: 'bi-x-circle' })
    }
  }

  async function downloadBatch(entries: { fileId: string; filename: string }[]) {
    if (!window.electron?.selectFolder) return

    const destDir = await window.electron.selectFolder()
    if (!destDir) return

    log.info('downloadBatch', { destDir, count: entries.length })
    try {
      await Promise.all(
        entries.map(({ fileId, filename }) => {
          const url = `${getApiBase()}/files/${fileId}/download`
          const destPath = `${destDir.replace(/\\/g, '/')}/${filename}`
          return window.electron!.downloadToPath(url, destPath)
        }),
      )
      log.info('downloadBatch done', { count: entries.length })
      const normalizedDir = destDir.replace(/\\/g, '/')
      toast.show(t('toast.batch_saved', { count: entries.length }), {
        type: 'success',
        icon: 'bi-check-circle',
        action: window.electron?.showItemInFolder && entries.length > 0
          ? { label: t('toast.open_folder'), callback: () => window.electron!.showItemInFolder(`${normalizedDir}/${entries[0].filename}`) }
          : undefined,
      })
    } catch (e) {
      log.error('downloadBatch failed', { error: e })
      toast.show(t('toast.batch_save_failed'), { type: 'error', icon: 'bi-x-circle' })
    }
  }

  return { downloadFile, downloadBatch }
}
