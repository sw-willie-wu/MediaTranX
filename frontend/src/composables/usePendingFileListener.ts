import { onActivated, onDeactivated } from 'vue'
import { useFilesStore } from '@/stores/files'
import type { PendingResultRef } from '@/stores/files'

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
  handleExistingFiles?: (refs: PendingResultRef[]) => void,
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
  const onPendingResultsReady = () => {
    const refs = filesStore.consumePendingResults()
    if (refs.length > 0) handleExistingFiles?.(refs)
  }

  onActivated(() => {
    window.addEventListener('pending-file-ready', onPendingReady)
    window.addEventListener('pending-files-ready', onPendingFilesReady)
    window.addEventListener('pending-results-ready', onPendingResultsReady)
  })
  onDeactivated(() => {
    window.removeEventListener('pending-file-ready', onPendingReady)
    window.removeEventListener('pending-files-ready', onPendingFilesReady)
    window.removeEventListener('pending-results-ready', onPendingResultsReady)
  })
}
