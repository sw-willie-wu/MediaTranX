import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { useFileDownload, collectLatestOutputs } from '@/composables/useFileDownload'
import { usePendingFileListener } from '@/composables/usePendingFileListener'
import { apiFetch } from '@/composables/useApi'
import { useMediaCollection } from '@/composables/useMediaCollection'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/logger'
import type { HistoryEntry } from '@/composables/useMediaCollection'

const log = createLogger('ImageWorkspace')

const IMAGE_EXTS = new Set([
  '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.tif',
  '.svg', '.ico', '.avif', '.heic', '.heif',
])

export interface ImageInfo {
  width: number
  height: number
  format: string
  mode: string
  file_size: number
}

/**
 * Generate a ~128px-wide thumbnail blob URL from a File.
 * Returns a blob: URL that the caller owns (revoke when done).
 */
export async function generateImageThumbnail(file: File, existingUrl?: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    // Reuse the already-created URL when available to avoid a second decode
    const objectUrl = existingUrl ?? URL.createObjectURL(file)
    const shouldRevoke = !existingUrl

    img.onload = () => {
      const TARGET_WIDTH = 128
      const scale = Math.min(1, TARGET_WIDTH / img.naturalWidth)
      const w = Math.round(img.naturalWidth * scale)
      const h = Math.round(img.naturalHeight * scale)

      const canvas = document.createElement('canvas')
      canvas.width = w
      canvas.height = h
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        if (shouldRevoke) URL.revokeObjectURL(objectUrl)
        reject(new Error('Cannot get 2D context'))
        return
      }
      ctx.drawImage(img, 0, 0, w, h)
      if (shouldRevoke) URL.revokeObjectURL(objectUrl)

      canvas.toBlob((blob) => {
        if (!blob) {
          reject(new Error('Canvas toBlob failed'))
          return
        }
        resolve(URL.createObjectURL(blob))
      }, 'image/jpeg', 0.8)
    }

    img.onerror = () => {
      if (shouldRevoke) URL.revokeObjectURL(objectUrl)
      reject(new Error('Image load failed'))
    }

    img.src = objectUrl
  })
}

export function useImageWorkspace() {
  const router = useRouter()
  const filesStore = useFilesStore()
  const taskStore = useTaskStore()
  const toast = useToast()
  const { downloadFile, downloadBatch } = useFileDownload()
  const { t } = useI18n()

  // ── Collection (multi-image state) ──────────────────────────────────────────
  const TEXT_RE = /\.(txt|md|json|csv|srt|vtt)$/i
  const collection = useMediaCollection({
    shouldAddToHistory: (result) => {
      const filename = result.output_filename as string | undefined
      return !TEXT_RE.test(filename ?? '')
    },
  })

  // ── Image-specific state (not per-entry, lives here) ────────────────────────
  const imageInfo = ref<ImageInfo | null>(null)
  const isLoadingInfo = ref(false)


  // ── Derived from active entry ────────────────────────────────────────────────

  /** True when at least one entry exists */
  const hasFile = computed(() => collection.hasEntries.value)

  /** The backend file-id of the active entry (original upload) */
  const fileId = computed<string | null>(() => collection.activeEntry.value?.fileId ?? null)

  /** Upload in progress for the active entry */
  const isUploading = computed<boolean>(
    () => collection.activeEntry.value?.status === 'uploading',
  )

  /** Source directory of the active entry */
  const sourceDir = computed<string | undefined>(
    () => collection.activeEntry.value?.sourceDir,
  )

  /** Original filename of the active entry */
  const currentFileName = computed<string>(
    () => collection.activeEntry.value?.file.name ?? '',
  )

  /** History stack of the active entry */
  const historyStack = computed<HistoryEntry[]>(
    () => collection.activeEntry.value?.historyStack ?? [],
  )

  const redoStack = computed<HistoryEntry[]>(
    () => collection.activeEntry.value?.redoStack ?? [],
  )

  const canGoBack = computed(() => historyStack.value.length > 0)
  const canGoForward = computed(() => redoStack.value.length > 0)

  /** The file-id to operate on: latest result, or original upload */
  const activeFileId = computed<string | null>(
    () => historyStack.value.at(-1)?.fileId ?? fileId.value,
  )

  /** Preview URL: latest result if available, otherwise original file preview */
  const activePreviewUrl = computed<string | null>(
    () => historyStack.value.at(-1)?.previewUrl ?? collection.activeEntry.value?.previewUrl ?? null,
  )

  const hasResult = computed(() => canGoBack.value)

  /**
   * Compute cumulative spatial transform from history stack.
   * Each crop records its offset/size relative to its input image; an upscale
   * changes the pixel grid but not the represented region in the original.
   * We walk the stack and compose a viewport (vx, vy, vw, vh) in original-image
   * coordinates so ComparisonSlider can correctly align multi-step results.
   */
  const activeResultMeta = computed<Record<string, unknown> | undefined>(() => {
    const stack = historyStack.value
    if (stack.length === 0) return undefined

    const hasCrop = stack.some((e) => e.meta?.crop_x != null)
    if (!hasCrop) {
      // No spatial crop — simple merge (e.g. upscale-only, filter-only)
      const merged: Record<string, unknown> = {}
      for (const entry of stack) {
        if (entry.meta) Object.assign(merged, entry.meta)
      }
      return Object.keys(merged).length > 0 ? merged : undefined
    }

    // Accumulate a viewport in original-image coordinates
    let vx = 0
    let vy = 0
    let vw: number | null = null
    let vh: number | null = null
    let baseW: number | null = null
    let baseH: number | null = null

    for (const entry of stack) {
      const m = entry.meta
      if (!m || m.crop_x == null) continue

      const cropX = m.crop_x as number
      const cropY = m.crop_y as number
      const cropW = m.crop_width as number
      const cropH = m.crop_height as number
      const srcW = m.source_width as number
      const srcH = m.source_height as number

      if (vw == null || vh == null) {
        // First crop — initialise viewport from its source (= original or upscaled original)
        baseW = srcW
        baseH = srcH
        vw = srcW
        vh = srcH
      }

      // Map crop coordinates from the current pixel grid back to original-image
      // coordinates. Explicit `: number` + `!` breaks a TS circular-inference
      // (vw/vh are `let`s reassigned below in this loop; the `if` block above
      // guarantees both are non-null here).
      const sx: number = vw! / srcW
      const sy: number = vh! / srcH
      vx += cropX * sx
      vy += cropY * sy
      vw = cropW * sx
      vh = cropH * sy
    }

    if (vw == null || baseW == null) return undefined

    return {
      crop_x: vx,
      crop_y: vy,
      crop_width: vw,
      crop_height: vh,
      source_width: baseW,
      source_height: baseH,
    }
  })

  /** Current task ID being processed for the active entry */
  const currentTaskId = computed<string | null>(
    () => collection.activeEntry.value?.currentTaskId ?? null,
  )

  // ── Helpers ──────────────────────────────────────────────────────────────────


  async function loadImageInfo() {
    if (!activeFileId.value) return
    isLoadingInfo.value = true
    try {
      const resp = await apiFetch(`/image/info/${activeFileId.value}`)
      if (!resp.ok) throw new Error('無法取得圖片資訊')
      imageInfo.value = await resp.json()
    } catch (e) {
      console.error('loadImageInfo error:', e)
    } finally {
      isLoadingInfo.value = false
    }
  }

  // ── Methods ──────────────────────────────────────────────────────────────────

  /**
   * Add and upload a single file.
   * Replaces the old handleFile(file, srcDir) signature exactly.
   */
  async function handleFile(file: File, srcDir?: string) {
    const ext = ('.' + file.name.split('.').pop()!).toLowerCase()
    if (!IMAGE_EXTS.has(ext)) {
      log.warn('handleFile skipped unsupported format', { fileName: file.name, ext })
      toast.show(`不支援的格式：${ext}`, { type: 'error', icon: 'bi-x-circle' })
      return
    }
    log.info('handleFile', { fileName: file.name, size: file.size, srcDir })
    imageInfo.value = null

    // Add entry to collection (generates thumbnail, sets status = 'uploading')
    const entryId = await collection.addEntry(file, srcDir, generateImageThumbnail)

    try {
      const uploadedFileId = await filesStore.uploadFile(file, srcDir)
      log.info('handleFile uploaded', { fileName: file.name, fileId: uploadedFileId })
      collection.updateEntry(entryId, { fileId: uploadedFileId, status: 'idle' })
      await loadImageInfo()
    } catch (e: any) {
      log.error('handleFile upload failed', { fileName: file.name, error: e.message })
      collection.updateEntry(entryId, { status: 'idle' })
      toast.show(e.message || '上傳失敗', { type: 'error', icon: 'bi-x-circle' })
    }
  }

  /**
   * Add multiple files at once (for batch drop / filmstrip).
   */
  async function handleFiles(files: File[]) {
    for (const file of files) {
      await handleFile(file)
    }
  }

  usePendingFileListener(handleFile, handleFiles)

  function handleRemoveFile() {
    const id = collection.activeId.value
    if (id) {
      collection.removeEntry(id)
    }
    if (!collection.hasEntries.value) {
      imageInfo.value = null
      isLoadingInfo.value = false
    }
  }

  function handlePanelSubmit(taskId: string) {
    const id = collection.activeId.value
    log.info('handlePanelSubmit', { taskId, entryId: id })
    if (id) {
      collection.registerTask(taskId, id)
      collection.updateEntry(id, { currentTaskId: taskId, status: 'processing' })
    }
  }

  function handleDownload() {
    const latest = historyStack.value.at(-1)
    if (!latest) return
    downloadFile(latest.fileId, latest.outputFilename, sourceDir.value)
  }

  /**
   * Undo last result for the active entry.
   */
  function goBack() {
    const id = collection.activeId.value
    if (!id) return
    const popped = historyStack.value.at(-1)
    log.info('goBack', { entryId: id, fromDepth: historyStack.value.length })
    const stack = historyStack.value.slice(0, -1)
    const redo = popped ? [...redoStack.value, popped] : redoStack.value
    collection.updateEntry(id, { historyStack: stack, redoStack: redo })
    loadImageInfo()
  }

  function goForward() {
    const id = collection.activeId.value
    if (!id) return
    const restored = redoStack.value.at(-1)
    if (!restored) return
    log.info('goForward', { entryId: id, redoDepth: redoStack.value.length })
    const stack = [...historyStack.value, restored]
    const redo = redoStack.value.slice(0, -1)
    collection.updateEntry(id, { historyStack: stack, redoStack: redo })
    loadImageInfo()
  }

  /**
   * Save latest result (or original) of every selected entry to a user-chosen folder.
   */
  async function handleDownloadBatch() {
    const entries = await collectLatestOutputs(
      [...collection.selectedIds.value],
      collection.entries.value,
    )
    if (entries.length === 0) {
      toast.show(t('common.no_exportable'), { type: 'info', icon: 'bi-info-circle' })
      return
    }
    await downloadBatch(entries)
  }

  // ── Watchers ─────────────────────────────────────────────────────────────────

  // Reload imageInfo when active entry changes
  watch(
    () => collection.activeId.value,
    () => {
      imageInfo.value = null
      if (collection.activeEntry.value?.fileId) {
        loadImageInfo()
      }
    },
  )

  // Reload imageInfo whenever activeFileId changes (e.g. after any task completes
  // and pushes a new history entry, or after goBack pops one).
  watch(activeFileId, (newId, oldId) => {
    if (newId && newId !== oldId) {
      loadImageInfo()
    }
  })

  // Watch for task completion on the active entry to handle TEXT results.
  // Image results are already pushed into historyStack by useMediaCollection's watcher.
  const _notifiedTaskIds = new Set<string>()
  watch(
    () => {
      const taskId = currentTaskId.value
      return taskId ? taskStore.tasks.get(taskId) : null
    },
    (task) => {
      if (!task) return
      if (task.status === 'completed' && task.result) {
        if (_notifiedTaskIds.has(task.taskId)) return
        _notifiedTaskIds.add(task.taskId)
        const r = task.result as { output_file_id?: string; output_filename?: string; output_dir?: string }
        if (r.output_file_id) {
          log.info('task completed', {
            taskId: task.taskId, taskType: task.taskType,
            outputFileId: r.output_file_id,
          })
          // Image output: historyStack already updated by useMediaCollection's watcher.
          // Reload imageInfo and show toast here. Text outputs (OCR) land in Results drawer.
          loadImageInfo()
          toast.show(t('toast.task_completed', { label: task.label ?? '' }), {
            type: 'success',
            icon: 'bi-check-circle',
          })
        }
      }
    },
    { deep: true },
  )

  // ── Return API (kept 100% stable for existing panels) ────────────────────────
  return {
    // Existing scalar/computed surface — all panels continue to work unchanged
    hasFile,
    fileId,
    isUploading,
    sourceDir,
    currentFileName,
    imageInfo,
    isLoadingInfo,
    currentTaskId,
    canGoBack,
    canGoForward,
    activeFileId,
    activePreviewUrl,
    hasResult,
    activeResultMeta,
    historyStack,

    // Existing methods
    goBack,
    goForward,
    loadImageInfo,
    handleFile,
    handleRemoveFile,
    handlePanelSubmit,
    handleDownload,

    // New additions
    collection,
    activeId: collection.activeId,
    selectedIds: collection.selectedIds,
    handleFiles,
    handleDownloadBatch,
  }
}
