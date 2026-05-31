import { ref, computed, watch, onActivated, onDeactivated } from 'vue'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { useFileDownload, collectLatestOutputs } from '@/composables/useFileDownload'
import { useMediaCollection } from '@/composables/useMediaCollection'
import { usePendingFileListener } from '@/composables/usePendingFileListener'
import { renderGlyphThumbnail, TOOL_GLYPH } from '@/utils/glyphThumbnail'
import { useExistingFileHandler } from '@/composables/useExistingFileHandler'
import { apiFetch } from '@/composables/useApi'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/logger'

const log = createLogger('VideoWorkspace')

const VIDEO_EXTS = new Set([
  '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm',
  '.m4v', '.mpg', '.mpeg', '.ts', '.3gp', '.vob',
])

export interface VideoMediaInfo {
  duration: number
  width: number
  height: number
  fps: number
  video_codec: string
  audio_codec: string
  bitrate: number
  file_size: number
}

function generateFallbackThumbnail(): string {
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = '#1e293b'
  ctx.fillRect(0, 0, size, size)
  ctx.fillStyle = '#64748b'
  ctx.font = '48px serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText('\u{1F3AC}', size / 2, size / 2)
  return canvas.toDataURL('image/png')
}

/**
 * Generate video thumbnail by capturing the first frame
 */
async function generateVideoThumbnail(_file: File, previewUrl: string): Promise<string> {
  return new Promise((resolve) => {
    const video = document.createElement('video')
    video.src = previewUrl
    video.crossOrigin = 'anonymous'
    video.muted = true
    video.preload = 'auto'

    let attempts = 0
    const seekTimes = [1, 3, 5, 0]  // 嘗試多個時間點

    const timeoutId = setTimeout(() => {
      resolve(generateFallbackThumbnail())
    }, 8000)

    function tryCapture() {
      const vw = video.videoWidth || 128
      const vh = video.videoHeight || 128
      const maxDim = 256
      const scale = Math.min(maxDim / vw, maxDim / vh)
      const cw = Math.round(vw * scale)
      const ch = Math.round(vh * scale)

      const canvas = document.createElement('canvas')
      canvas.width = cw
      canvas.height = ch
      const ctx = canvas.getContext('2d')!
      ctx.drawImage(video, 0, 0, cw, ch)

      // 偵測是否為黑畫面（取樣中心 pixel 的亮度）
      const sample = ctx.getImageData(Math.floor(cw / 2), Math.floor(ch / 2), 1, 1).data
      const brightness = sample[0] + sample[1] + sample[2]

      if (brightness < 30 && attempts < seekTimes.length - 1) {
        // 太暗，嘗試下一個時間點
        attempts++
        video.currentTime = seekTimes[attempts]
        return  // 等下一次 seeked 事件
      }

      // 亮度足夠或已嘗試所有時間點
      canvas.toBlob((blob) => {
        resolve(blob ? URL.createObjectURL(blob) : generateFallbackThumbnail())
      }, 'image/jpeg', 0.7)
    }

    video.addEventListener('seeked', tryCapture)

    video.addEventListener('error', () => {
      clearTimeout(timeoutId)
      resolve(generateFallbackThumbnail())
    }, { once: true })

    // 開始第一次 seek
    video.currentTime = seekTimes[0]
  })
}

export function useVideoWorkspace() {
  const filesStore = useFilesStore()
  const taskStore = useTaskStore()
  const toast = useToast()
  const { downloadFile, downloadBatch } = useFileDownload()
  const { t } = useI18n()

  // ── Collection (multi-video state) ──
  const VIDEO_OUTPUT_TASKS = new Set(['video.transcode', 'video.cut', 'video.crop', 'video.enhance', 'video.interpolate'])
  const collection = useMediaCollection({
    shouldAddToHistory: (_result, taskType) => VIDEO_OUTPUT_TASKS.has(taskType),
  })

  // ── Video-specific state ──
  const mediaInfo = ref<VideoMediaInfo | null>(null)

  // ── Derived from active entry ──
  const hasFile = computed(() => collection.hasEntries.value)
  const fileId = computed<string | null>(() => collection.activeEntry.value?.fileId ?? null)
  const isUploading = computed<boolean>(() => collection.activeEntry.value?.status === 'uploading')
  const sourceDir = computed<string | undefined>(() => collection.activeEntry.value?.sourceDir)
  const currentFileName = computed<string>(() => collection.activeEntry.value?.fileName ?? '')
  const currentTaskId = computed<string | null>(() => collection.activeEntry.value?.currentTaskId ?? null)
  const historyStack = computed(() => collection.activeEntry.value?.historyStack ?? [])

  const redoStack = computed(() => collection.activeEntry.value?.redoStack ?? [])
  const hasResult = computed<boolean>(() => historyStack.value.length > 0)
  const canGoBack = computed(() => historyStack.value.length > 0)
  const canGoForward = computed(() => redoStack.value.length > 0)

  /** Preview URL: latest result if available, otherwise original */
  const activePreviewUrl = computed<string | null>(
    () => historyStack.value.at(-1)?.previewUrl ?? collection.activeEntry.value?.previewUrl ?? null,
  )

  /** File ID for panels: latest result, or original */
  const activeFileId = computed<string | null>(
    () => historyStack.value.at(-1)?.fileId ?? fileId.value,
  )

  async function loadMediaInfo() {
    const fid = activeFileId.value
    if (!fid) return
    try {
      const response = await apiFetch(`/video/info/${fid}`)
      if (response.ok) mediaInfo.value = await response.json()
    } catch (e) {
      console.error('Failed to load media info:', e)
    }
  }

  // Reload media info when active entry or result file changes
  watch([() => collection.activeId.value, activeFileId], async () => {
    mediaInfo.value = null
    if (fileId.value) await loadMediaInfo()
  })

  async function handleFile(file: File, srcDir?: string) {
    const ext = ('.' + file.name.split('.').pop()!).toLowerCase()
    if (!VIDEO_EXTS.has(ext)) {
      log.warn('handleFile skipped unsupported format', { fileName: file.name, ext })
      toast.show(`不支援的格式：${ext}`, { type: 'error', icon: 'bi-x-circle' })
      return
    }
    log.info('handleFile', { fileName: file.name, size: file.size, srcDir })
    mediaInfo.value = null

    const entryId = await collection.addEntry(file, srcDir, generateVideoThumbnail)

    try {
      const uploadedFileId = await filesStore.uploadFile(file, srcDir)
      log.info('handleFile uploaded', { fileName: file.name, fileId: uploadedFileId })
      collection.updateEntry(entryId, { fileId: uploadedFileId, status: 'idle' })
      await loadMediaInfo()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      log.error('handleFile upload failed', { fileName: file.name, error: msg })
      collection.updateEntry(entryId, { status: 'idle' })
      toast.show(msg || '上傳失敗', { type: 'error', icon: 'bi-x-circle' })
    }
  }

  async function handleFiles(files: File[]) {
    for (const file of files) {
      const srcDir = window.electron?.getFileSourceDir?.(file.name, file.size, file.lastModified) ?? undefined
      await handleFile(file, srcDir)
    }
  }

  const { handleExistingFiles } = useExistingFileHandler(
    collection, loadMediaInfo, () => renderGlyphThumbnail(TOOL_GLYPH.video),
  )
  usePendingFileListener(handleFile, handleFiles, handleExistingFiles)

  // Completed URL downloads are adopted ONLY by the Video tool, and only while
  // it is active (avoids touching an inactive/cached component's DOM). Drains on
  // activation (picks up anything queued while away) and on the video-only event
  // (download finished while the Video tool was already open).
  function drainVideoDownloads() {
    const refs = filesStore.consumeVideoDownloads()
    if (refs.length > 0) handleExistingFiles(refs)
  }
  onActivated(() => {
    window.addEventListener('video-download-ready', drainVideoDownloads)
    drainVideoDownloads()
  })
  onDeactivated(() => {
    window.removeEventListener('video-download-ready', drainVideoDownloads)
  })

  function handleRemoveFile() {
    const id = collection.activeId.value
    if (id) {
      collection.removeEntry(id)
    }
    if (!collection.hasEntries.value) {
      mediaInfo.value = null
    }
  }

  function handlePanelSubmit(taskId: string) {
    log.info('handlePanelSubmit', { taskId })
    const entry = collection.activeEntry.value
    if (entry) {
      collection.registerTask(taskId, entry.id)
      collection.updateEntry(entry.id, { currentTaskId: taskId, status: 'processing' })
    }
  }

  function handleDownload(outputFormat?: string, _suffix = '_output') {
    // Binary result download (from history stack)
    const latest = historyStack.value.at(-1)
    if (latest) {
      downloadFile(latest.fileId, latest.outputFilename, sourceDir.value)
      return
    }
  }

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

  // Watch for task completion
  const _notifiedTaskIds = new Set<string>()
  watch(
    () => currentTaskId.value ? taskStore.tasks.get(currentTaskId.value) : null,
    (task) => {
      if (!task || task.status !== 'completed' || !task.result) return
      if (_notifiedTaskIds.has(task.taskId)) return
      _notifiedTaskIds.add(task.taskId)

      const r = task.result as { output_file_id?: string }
      if (!r.output_file_id) return
      log.info('task completed', { taskId: task.taskId, taskType: task.taskType, outputFileId: r.output_file_id })

      toast.show(t('toast.task_completed', { label: task.label ?? '' }), {
        type: 'success',
        icon: 'bi-check-circle',
      })
    },
    { deep: true }
  )

  function goBack() {
    const id = collection.activeId.value
    if (!id) return
    const popped = historyStack.value.at(-1)
    log.info('goBack', { entryId: id, fromDepth: historyStack.value.length })
    const stack = historyStack.value.slice(0, -1)
    const redo = popped ? [...redoStack.value, popped] : redoStack.value
    collection.updateEntry(id, { historyStack: stack, redoStack: redo })
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
  }

  return {
    hasFile,
    fileId,
    activeFileId,
    activePreviewUrl,
    isUploading,
    sourceDir,
    currentFileName,
    mediaInfo,
    currentTaskId,
    hasResult,
    canGoBack,
    canGoForward,
    collection,
    handleFile,
    handleFiles,
    handleRemoveFile,
    handlePanelSubmit,
    handleDownload,
    handleDownloadBatch,
    handleExistingFiles,
    goBack,
    goForward,
  }
}
