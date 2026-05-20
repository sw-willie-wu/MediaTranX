import { onActivated, onDeactivated } from 'vue'
import { useFilesStore } from '@/stores/files'

/**
 * Listen for cross-tool "open in this tool" events while the view is active.
 *
 * Uses onActivated/onDeactivated (not onMounted/onBeforeUnmount) so that views
 * under <KeepAlive> only receive the event while they're the visible route —
 * otherwise deactivated workspaces would race to consume the pending file.
 */
export function usePendingFileListener(
  handleFile: (file: File, sourceDir?: string) => void,
  handleFiles?: (files: File[]) => void,
) {
  const filesStore = useFilesStore()

  const onPendingReady = () => {
    const p = filesStore.consumePendingFile()
    if (p) handleFile(p.file, p.sourceDir)
  }
  const onPendingFilesReady = () => {
    const many = filesStore.consumePendingFiles()
    if (many.length > 0) handleFiles?.(many)
  }

  onActivated(() => {
    window.addEventListener('pending-file-ready', onPendingReady)
    window.addEventListener('pending-files-ready', onPendingFilesReady)
  })
  onDeactivated(() => {
    window.removeEventListener('pending-file-ready', onPendingReady)
    window.removeEventListener('pending-files-ready', onPendingFilesReady)
  })
}
