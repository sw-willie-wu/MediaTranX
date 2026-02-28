/**
 * 下載後端產出檔案到本機
 * 透過 Electron saveFileDialog 讓用戶選擇儲存路徑，再由 IPC 寫入磁碟
 */
import { useToast } from './useToast'

const toast = useToast()

export function useFileDownload() {
  async function downloadFile(fileId: string, defaultName: string, defaultDir?: string) {
    if (!window.electron?.saveFileDialog) return

    const ext = defaultName.split('.').pop() ?? ''
    const filters = ext
      ? [{ name: ext.toUpperCase(), extensions: [ext] }, { name: '所有檔案', extensions: ['*'] }]
      : [{ name: '所有檔案', extensions: ['*'] }]

    // 組合預設儲存路徑：若有原始目錄則用，否則只帶檔名讓系統決定位置
    const defaultPath = defaultDir
      ? `${defaultDir.replace(/\\/g, '/')}/${defaultName}`
      : defaultName

    const destPath = await window.electron.saveFileDialog({
      title: '儲存結果',
      defaultPath,
      filters,
    })
    if (!destPath) return

    try {
      await window.electron.downloadToPath(
        `http://localhost:8001/api/files/${fileId}/download`,
        destPath,
      )
      toast.show('已儲存至指定位置', { type: 'success', icon: 'bi-check-circle' })
    } catch {
      toast.show('儲存失敗', { type: 'error', icon: 'bi-x-circle' })
    }
  }

  return { downloadFile }
}
