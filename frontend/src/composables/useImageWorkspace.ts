import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { useFileDownload } from '@/composables/useFileDownload'
import { apiFetch } from '@/composables/useApi'
import { useMediaCollection } from '@/composables/useMediaCollection'
import type { HistoryEntry } from '@/composables/useMediaCollection'

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
  const { downloadFile } = useFileDownload()

  // ── Collection (multi-image state) ──────────────────────────────────────────
  const collection = useMediaCollection()

  // ── Image-specific state (not per-entry, lives here) ────────────────────────
  const imageInfo = ref<ImageInfo | null>(null)
  const isLoadingInfo = ref(false)

  // 文字輸出結果（OCR 等非圖片任務）
  const textResultFileId = ref<string | null>(null)
  const textResultFilename = ref<string | null>(null)
  const textResultContent = ref<string | null>(null)

  const aiEnvReady = ref(false)

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

  const canGoBack = computed(() => historyStack.value.length > 0)

  /** The file-id to operate on: latest result, or original upload */
  const activeFileId = computed<string | null>(
    () => historyStack.value.at(-1)?.fileId ?? fileId.value,
  )

  /** Preview URL: latest result if available, otherwise original file preview */
  const activePreviewUrl = computed<string | null>(
    () => historyStack.value.at(-1)?.previewUrl ?? collection.activeEntry.value?.previewUrl ?? null,
  )

  const hasResult = computed(() => canGoBack.value || !!textResultFileId.value)

  /** Current task ID being processed for the active entry */
  const currentTaskId = computed<string | null>(
    () => collection.activeEntry.value?.currentTaskId ?? null,
  )

  // ── Helpers ──────────────────────────────────────────────────────────────────

  async function checkAiEnvironment(currentFunction?: string) {
    try {
      const res = await apiFetch('/setup/status')
      const status = await res.json()
      aiEnvReady.value = status.ai_env_ready
      if (!aiEnvReady.value && currentFunction === 'upscale') {
        toast.show('超解析功能需要安裝 AI 核心環境', {
          type: 'info',
          action: { label: '去安裝', callback: () => router.push('/setup') },
        })
      }
    } catch (e) {
      console.error('Failed to check AI status', e)
    }
  }

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
    // Clear text results from the previous entry
    textResultFileId.value = null
    textResultFilename.value = null
    textResultContent.value = null
    imageInfo.value = null

    // Add entry to collection (generates thumbnail, sets status = 'uploading')
    const entryId = await collection.addEntry(file, srcDir, generateImageThumbnail)

    try {
      const uploadedFileId = await filesStore.uploadFile(file, srcDir)
      collection.updateEntry(entryId, { fileId: uploadedFileId, status: 'idle' })
      await loadImageInfo()
    } catch (e: any) {
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

  function handleRemoveFile() {
    const id = collection.activeId.value
    if (id) {
      collection.removeEntry(id)
    }
    if (!collection.hasEntries.value) {
      imageInfo.value = null
      textResultFileId.value = null
      textResultFilename.value = null
      textResultContent.value = null
      isLoadingInfo.value = false
    }
  }

  function handlePanelSubmit(taskId: string) {
    const id = collection.activeId.value
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

  function handleTextDownload() {
    if (!textResultFileId.value || !textResultFilename.value) return
    downloadFile(textResultFileId.value, textResultFilename.value, sourceDir.value)
  }

  /**
   * Undo last result for the active entry.
   */
  function goBack() {
    const id = collection.activeId.value
    if (!id) return
    const stack = historyStack.value.slice(0, -1)
    collection.updateEntry(id, { historyStack: stack })
    loadImageInfo()
  }

  /**
   * Batch export placeholder — implemented in Step 9.
   */
  function handleDownloadBatch() {
    // TODO: Step 9 — iterate selectedIds and download each entry's latest result
    toast.show('批次下載尚未實作', { type: 'info' })
  }

  // ── Watchers ─────────────────────────────────────────────────────────────────

  // Reload imageInfo when active entry changes
  watch(
    () => collection.activeId.value,
    () => {
      imageInfo.value = null
      textResultFileId.value = null
      textResultFilename.value = null
      textResultContent.value = null
      if (collection.activeEntry.value?.fileId) {
        loadImageInfo()
      }
    },
  )

  // Watch for task completion on the active entry to handle TEXT results.
  // Image results are already pushed into historyStack by useMediaCollection's watcher.
  watch(
    () => {
      const taskId = currentTaskId.value
      return taskId ? taskStore.tasks.get(taskId) : null
    },
    (task) => {
      if (!task) return
      if (task.status === 'completed' && task.result) {
        const r = task.result as { output_file_id?: string; output_filename?: string }
        if (r.output_file_id) {
          const isText = /\.(txt|md|json|csv|srt|vtt)$/i.test(r.output_filename ?? '')
          if (isText) {
            // Text output (OCR etc.): store for preview/download, do not push to historyStack
            textResultFileId.value = r.output_file_id
            textResultFilename.value =
              r.output_filename ??
              `${currentFileName.value.replace(/\.[^.]+$/, '')}_ocr.txt`
            apiFetch(`/files/${r.output_file_id}/download`)
              .then((res) => (res.ok ? res.text() : null))
              .then((text) => {
                textResultContent.value = text
              })
              .catch(() => {})
            toast.show(`${task.label ?? '處理'} 完成`, {
              type: 'success',
              icon: 'bi-check-circle',
              action: { label: '下載', callback: () => handleTextDownload() },
            })
          } else {
            // Image output: historyStack already updated by useMediaCollection's watcher.
            // Reload imageInfo and show toast here.
            loadImageInfo()
            toast.show(`${task.label ?? '處理'} 完成`, {
              type: 'success',
              icon: 'bi-check-circle',
              action: { label: '下載', callback: () => handleDownload() },
            })
          }
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
    aiEnvReady,
    canGoBack,
    activeFileId,
    activePreviewUrl,
    hasResult,
    historyStack,
    textResultFileId,
    textResultFilename,
    textResultContent,

    // Existing methods
    goBack,
    checkAiEnvironment,
    loadImageInfo,
    handleFile,
    handleRemoveFile,
    handlePanelSubmit,
    handleDownload,
    handleTextDownload,

    // New additions
    collection,
    activeId: collection.activeId,
    selectedIds: collection.selectedIds,
    handleFiles,
    handleDownloadBatch,
  }
}
