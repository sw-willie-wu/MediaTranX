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

/**
 * 對齊 expandDropItems 的上限語意,套用在 webkitdirectory input 回傳的扁平清單:
 * 深度 > MAX_DEPTH 靜默略過(同 walk 的 depth guard;邊界 depth 8 收、9 濾)、
 * 過濾後超過 MAX_FILES 截斷並回報 truncated。
 * 深度 = webkitRelativePath 的目錄層數('root/a.jpg' → 1,與 walk depth 一致);
 * 空 webkitRelativePath 為防禦分支(webkitdirectory 來源必有值),視為深度 0 照收。
 * 註:>MAX_FILES 時保留的檔案集合(FileList 順序)與拖曳(DFS 順序)不保證逐檔相同,
 * 僅數量與 truncated 旗標一致。
 */
export function capFolderFiles(all: File[]): DropExpansion {
  const files = all.filter((f) => {
    const rel = f.webkitRelativePath
    const depth = rel ? rel.split('/').length - 1 : 0
    return depth <= MAX_DEPTH
  })
  if (files.length > MAX_FILES) {
    return { files: files.slice(0, MAX_FILES), truncated: true }
  }
  return { files, truncated: false }
}
