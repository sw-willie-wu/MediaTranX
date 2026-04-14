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
  async function downloadFile(fileId: string, defaultName: string, defaultDir?: string): Promise<string | null> {
    if (!window.electron?.saveFileDialog) return null

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
    if (!destPath) return null

    // Try to get the file's disk path for direct copy (skip HTTP)
    let srcPath: string | undefined
    try {
      const infoRes = await fetch(`${getApiBase()}/files/${fileId}`)
      if (infoRes.ok) {
        const info = await infoRes.json()
        srcPath = info.file_path
      }
    } catch {}

    log.info('downloadFile', { fileId, destPath, srcPath })
    try {
      await window.electron.downloadToPath(
        `${getApiBase()}/files/${fileId}/download`,
        destPath,
        srcPath,
      )
      log.info('downloadFile done', { fileId, destPath })
      toast.show(t('toast.saved'), {
        type: 'success',
        icon: 'bi-check-circle',
      })
      return destPath
    } catch (e) {
      log.error('downloadFile failed', { fileId, destPath, error: e })
      toast.show(t('toast.save_failed'), { type: 'error', icon: 'bi-x-circle' })
      return null
    }
  }

  async function downloadBatch(
    entries: { fileId: string; filename: string; srcPath?: string }[],
    onEach?: (fileId: string, destPath: string) => void,
  ): Promise<Map<string, string>> {
    /** Returns a map of fileId → savedPath for successfully written files.
     *  `onEach` is invoked per-file as soon as that file completes writing. */
    const saved = new Map<string, string>()
    if (!window.electron?.selectFolder) return saved

    const destDir = await window.electron.selectFolder()
    if (!destDir) return saved

    log.info('downloadBatch', { destDir, count: entries.length })
    const normalizedDir = destDir.replace(/\\/g, '/')
    try {
      await Promise.all(
        entries.map(async ({ fileId, filename, srcPath }) => {
          const url = `${getApiBase()}/files/${fileId}/download`
          const destPath = `${normalizedDir}/${filename}`
          try {
            await window.electron!.downloadToPath(url, destPath, srcPath)
            saved.set(fileId, destPath)
            onEach?.(fileId, destPath)
          } catch (e) {
            log.warn('batch entry failed', { fileId, destPath, e })
          }
        }),
      )
      log.info('downloadBatch done', { saved: saved.size, total: entries.length })
      toast.show(t('toast.batch_saved', { count: saved.size }), {
        type: 'success',
        icon: 'bi-check-circle',
      })
    } catch (e) {
      log.error('downloadBatch failed', { error: e })
      toast.show(t('toast.batch_save_failed'), { type: 'error', icon: 'bi-x-circle' })
    }
    return saved
  }

  return { downloadFile, downloadBatch }
}
