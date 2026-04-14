import { ref, computed, watch } from 'vue'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { useFileDownload, collectLatestOutputs } from '@/composables/useFileDownload'
import { useMediaCollection } from '@/composables/useMediaCollection'
import { usePendingFileListener } from '@/composables/usePendingFileListener'
import { apiFetch } from '@/composables/useApi'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/logger'

const log = createLogger('DocumentWorkspace')

const DOCUMENT_EXTS = new Set([
  '.pdf', '.doc', '.docx',
  '.txt', '.md', '.log',
  '.srt', '.vtt', '.lrc', '.ass',
])

/**
 * Generate a simple document thumbnail (document icon on dark background)
 */
async function generateDocumentThumbnail(_file: File, _previewUrl: string): Promise<string> {
  return new Promise((resolve) => {
    const size = 128
    const canvas = document.createElement('canvas')
    canvas.width = size
    canvas.height = size
    const ctx = canvas.getContext('2d')!

    // Dark background
    ctx.fillStyle = '#1e293b'
    ctx.fillRect(0, 0, size, size)

    // Document icon
    ctx.fillStyle = '#64748b'
    ctx.font = '48px serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText('\u{1F4C4}', size / 2, size / 2)

    canvas.toBlob((blob) => {
      if (blob) {
        resolve(URL.createObjectURL(blob))
      } else {
        resolve('')
      }
    }, 'image/png')
  })
}

export function useDocumentWorkspace() {
  const filesStore = useFilesStore()
  const taskStore = useTaskStore()
  const toast = useToast()
  const { downloadFile, downloadBatch } = useFileDownload()
  const { t } = useI18n()

  // ── Collection (multi-document state) ──
  const collection = useMediaCollection({
    shouldAddToHistory: (result) => !result.text_content && !result.text_file_id,
  })

  // ── Derived from active entry ──
  const hasFile = computed(() => collection.hasEntries.value)
  const fileId = computed<string | null>(() => collection.activeEntry.value?.fileId ?? null)
  const isUploading = computed<boolean>(() => collection.activeEntry.value?.status === 'uploading')
  const sourceDir = computed<string | undefined>(() => collection.activeEntry.value?.sourceDir)
  const currentFileName = computed<string>(() => collection.activeEntry.value?.file.name ?? '')
  const currentTaskId = computed<string | null>(() => collection.activeEntry.value?.currentTaskId ?? null)
  const historyStack = computed(() => collection.activeEntry.value?.historyStack ?? [])

  const hasResult = computed<boolean>(() => historyStack.value.length > 0)

  /** File ID for panels: latest result, or original */
  const activeFileId = computed<string | null>(
    () => historyStack.value.at(-1)?.fileId ?? fileId.value,
  )

  // OCR text result (for modal display)
  const textResultFileId   = ref<string | null>(null)
  const textResultFilename = ref<string | null>(null)
  const textResultContent  = ref<string | null>(null)

  async function handleFile(file: File, srcDir?: string) {
    const ext = ('.' + file.name.split('.').pop()!).toLowerCase()
    if (!DOCUMENT_EXTS.has(ext)) {
      log.warn('handleFile skipped unsupported format', { fileName: file.name, ext })
      toast.show(`不支援的格式：${ext}`, { type: 'error', icon: 'bi-x-circle' })
      return
    }
    log.info('handleFile', { fileName: file.name, size: file.size, srcDir })
    textResultContent.value = null
    textResultFileId.value = null
    textResultFilename.value = null

    const entryId = await collection.addEntry(file, srcDir, generateDocumentThumbnail)

    try {
      const uploadedFileId = await filesStore.uploadFile(file, srcDir)
      log.info('handleFile uploaded', { fileName: file.name, fileId: uploadedFileId })
      collection.updateEntry(entryId, { fileId: uploadedFileId, status: 'idle' })
    } catch (e: any) {
      log.error('handleFile upload failed', { fileName: file.name, error: e.message })
      collection.updateEntry(entryId, { status: 'idle' })
      toast.show(e.message || '上傳失敗', { type: 'error', icon: 'bi-x-circle' })
    }
  }

  async function handleFiles(files: File[]) {
    for (const file of files) {
      const srcDir = window.electron?.getFileSourceDir?.(file.name, file.size, file.lastModified) ?? undefined
      await handleFile(file, srcDir)
    }
  }

  usePendingFileListener(handleFile, handleFiles)

  function handleRemoveFile() {
    const id = collection.activeId.value
    if (id) {
      collection.removeEntry(id)
    }
    if (!collection.hasEntries.value) {
      textResultContent.value = null
      textResultFileId.value = null
      textResultFilename.value = null
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

  function handleDownload(fallbackSuffix = '_output', fallbackExt = 'pdf') {
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

  function handleTextDownload() {
    if (!textResultFileId.value || !textResultFilename.value) return
    downloadFile(textResultFileId.value, textResultFilename.value, sourceDir.value)
  }

  // Watch for task completion
  const _notifiedTaskIds = new Set<string>()
  watch(
    () => currentTaskId.value ? taskStore.tasks.get(currentTaskId.value) : null,
    async (task) => {
      if (!task || task.status !== 'completed' || !task.result) return
      if (_notifiedTaskIds.has(task.taskId)) return
      _notifiedTaskIds.add(task.taskId)
      const r = task.result as { output_file_id?: string; output_filename?: string }
      if (!r.output_file_id) return
      log.info('task completed', { taskId: task.taskId, taskType: task.taskType, outputFileId: r.output_file_id })

      // OCR task: load text content for modal display
      if (task.taskType === 'document.ocr') {
        textResultFileId.value   = r.output_file_id
        textResultFilename.value = r.output_filename ?? null
        try {
          const res = await apiFetch(`/files/${r.output_file_id}/download`)
          if (res.ok) textResultContent.value = await res.text()
        } catch {}
      } else {
        textResultContent.value = null
        textResultFileId.value = null
        textResultFilename.value = null
      }

      toast.show(t('toast.task_completed', { label: task.label ?? '' }), {
        type: 'success',
        icon: 'bi-check-circle',
      })
    },
    { deep: true },
  )

  // Reset text result when switching files
  watch(() => collection.activeId.value, () => {
    textResultFileId.value = null
    textResultFilename.value = null
    textResultContent.value = null
  })

  return {
    hasFile,
    fileId,
    activeFileId,
    isUploading,
    sourceDir,
    currentFileName,
    currentTaskId,
    hasResult,
    textResultFileId,
    textResultFilename,
    textResultContent,
    collection,
    handleFile,
    handleFiles,
    handleRemoveFile,
    handlePanelSubmit,
    handleDownload,
    handleDownloadBatch,
    handleTextDownload,
  }
}
