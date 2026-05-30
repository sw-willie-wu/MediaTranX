/**
 * 完成的 video.download 任務產物 → 排進「影片下載待入佇列」(影片專屬,只有影片
 * 工具會在 onActivated 時消費,不會被其他當前工具誤吃)+ 立即派發 video-only 事件
 * (影片工具若正 active 就即時載入)+ 顯示「下載完成、已載入」toast(按鈕＝前往影片工具)。
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
  useFilesStore().queueVideoDownload({
    fileId: result.output_file_id,
    filename: result.output_filename,
    fileSize: result.output_size,
    mimeType: 'video/mp4',
  })
  // Notify a mounted+active Video tool to pick it up immediately; if no Video
  // tool is active it stays queued and is drained on the tool's next activation.
  window.dispatchEvent(new CustomEvent('video-download-ready'))
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
