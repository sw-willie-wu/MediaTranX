import { useFilesStore } from '@/stores/files'
import type { PendingResultRef } from '@/stores/files'
import type { useMediaCollection } from '@/composables/useMediaCollection'

type Collection = Pick<ReturnType<typeof useMediaCollection>, 'addExistingEntry'>

/**
 * Shared logic for opening a backend-resident result file into a workspace
 * by reference (no download/upload). Used by the cross-tool "open in tool"
 * path and by MIDI compose output adoption.
 *
 * @param makeThumbnail Optional sync factory for the filmstrip thumbnail. Non-image
 *   domains pass a glyph-icon factory because the raw media download URL can't be
 *   rendered as an <img>. Omit for images (the download URL is itself a valid image).
 */
export function useExistingFileHandler(
  collection: Collection,
  loadInfo?: () => void | Promise<void>,
  makeThumbnail?: () => string,
) {
  const filesStore = useFilesStore()

  function addExistingFile(ref: PendingResultRef): string {
    const mediaFile = filesStore.adoptResultFile(ref)  // sets files map + currentFile
    const thumb = makeThumbnail?.()
    return collection.addExistingEntry({
      fileId: ref.fileId,
      fileName: ref.filename,
      fileSize: ref.fileSize,
      mimeType: ref.mimeType,
      previewUrl: mediaFile.previewUrl!,
      // Non-empty glyph thumbnail for non-image domains; else fall back to the
      // download URL (correct for images, whose URL renders as an <img>).
      thumbnailUrl: thumb || undefined,
    })
  }

  async function handleExistingFiles(refs: PendingResultRef[]): Promise<void> {
    for (const ref of refs) addExistingFile(ref)
    if (loadInfo) await loadInfo()
  }

  return { addExistingFile, handleExistingFiles }
}
