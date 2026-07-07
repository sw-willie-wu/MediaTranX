const MAX_DEPTH = 8
const MAX_FILES = 500

export interface DropExpansion {
  files: File[]
  truncated: boolean
}

/** True if any drop item is a directory (folder-aware path needed). */
export function hasDirectoryItem(items: DataTransferItemList): boolean {
  for (let i = 0; i < items.length; i++) {
    if (items[i].webkitGetAsEntry?.()?.isDirectory) return true
  }
  return false
}

/**
 * Expand DataTransferItems into File objects, descending into directories.
 * Entries are captured synchronously before any await — Chromium invalidates
 * DataTransferItemList after the drop event handler yields.
 * readEntries returns batches (≤100 in Chromium); loop until an empty batch.
 */
export async function expandDropItems(items: DataTransferItemList): Promise<DropExpansion> {
  const roots: FileSystemEntry[] = []
  for (let i = 0; i < items.length; i++) {
    const entry = items[i].webkitGetAsEntry?.()
    if (entry) roots.push(entry)
  }

  const files: File[] = []
  let truncated = false

  async function walk(entry: FileSystemEntry, depth: number): Promise<void> {
    if (files.length >= MAX_FILES) { truncated = true; return }
    if (entry.isFile) {
      const f = await new Promise<File | null>((resolve) =>
        (entry as FileSystemFileEntry).file(resolve, () => resolve(null)),
      )
      if (f) files.push(f)
      return
    }
    if (entry.isDirectory) {
      if (depth >= MAX_DEPTH) return
      const reader = (entry as FileSystemDirectoryEntry).createReader()
      for (;;) {
        const batch = await new Promise<FileSystemEntry[]>((resolve) =>
          reader.readEntries(resolve, () => resolve([])),
        )
        if (batch.length === 0) return
        for (const child of batch) {
          if (files.length >= MAX_FILES) { truncated = true; return }
          await walk(child, depth + 1)
        }
      }
    }
  }

  for (const root of roots) {
    if (files.length >= MAX_FILES) { truncated = true; break }
    await walk(root, 0)
  }
  return { files, truncated }
}
