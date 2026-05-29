import { useFilesStore } from '@/stores/files'
import type { PendingResultRef } from '@/stores/files'
import type { useMediaCollection } from '@/composables/useMediaCollection'

type Collection = Pick<ReturnType<typeof useMediaCollection>, 'addExistingEntry'>

/**
 * Shared logic for opening a backend-resident result file into a workspace
 * by reference (no download/upload). Used by the cross-tool "open in tool"
 * path and by MIDI compose output adoption.
 */
export function useExistingFileHandler(
  collection: Collection,
  loadInfo?: () => void | Promise<void>,
) {
  const filesStore = useFilesStore()

  function addExistingFile(ref: PendingResultRef): string {
    const mediaFile = filesStore.adoptResultFile(ref)  // sets files map + currentFile
    return collection.addExistingEntry({
      fileId: ref.fileId,
      fileName: ref.filename,
      fileSize: ref.fileSize,
      mimeType: ref.mimeType,
      previewUrl: mediaFile.previewUrl!,
    })
  }

  async function handleExistingFiles(refs: PendingResultRef[]): Promise<void> {
    for (const ref of refs) addExistingFile(ref)
    if (loadInfo) await loadInfo()
  }

  return { addExistingFile, handleExistingFiles }
}
