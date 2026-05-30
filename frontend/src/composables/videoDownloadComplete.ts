/**
 * 把完成的 video.download 任務產物,透過 Feature A 的 pending-results 通道
 * 接回影片工具(零重傳),並顯示帶「開啟」鈕的完成 toast(不自動跳頁)。
 */
import { useFilesStore } from '@/stores/files'
import { useToast } from '@/composables/useToast'
import i18n from '@/i18n'  // default export (i18n/index.ts:43 `export default i18n`)
import router from '@/router'

export interface CompletedDownload {
  output_file_id: string
  output_filename: string
  output_size: number
  title?: string
}

export function adoptCompletedDownload(result: CompletedDownload): void {
  useFilesStore().setPendingResults([
    {
      fileId: result.output_file_id,
      filename: result.output_filename,
      fileSize: result.output_size,
      mimeType: 'video/mp4',
    },
  ])
  window.dispatchEvent(new Event('pending-results-ready'))
  useToast().show(
    i18n.global.t('video_download.toast.complete', { title: result.title || '' }),
    {
      type: 'success',
      action: {
        label: i18n.global.t('video_download.toast.open'),
        callback: () => router.push('/video'),
      },
    },
  )
}
