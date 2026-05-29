import { ref, computed, watch } from 'vue'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { useFileDownload, collectLatestOutputs } from '@/composables/useFileDownload'
import { useMediaCollection } from '@/composables/useMediaCollection'
import { usePendingFileListener } from '@/composables/usePendingFileListener'
import { useExistingFileHandler } from '@/composables/useExistingFileHandler'
import { apiFetch } from '@/composables/useApi'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/logger'

const log = createLogger('AudioWorkspace')

// 支援的音訊格式
const AUDIO_EXTS = new Set([
  '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a',
  '.opus', '.amr', '.ape', '.ac3', '.dts', '.aiff', '.aif',
  '.mid', '.midi',
])

export interface AudioInfo {
  duration: number
  sample_rate: number
  channels: number
  codec: string
  bitrate: number
  file_size: number
}

/**
 * Generate a simple audio thumbnail (music note icon on dark background)
 */
async function generateAudioThumbnail(_file: File, _previewUrl: string): Promise<string> {
  return new Promise((resolve) => {
    const size = 128
    const canvas = document.createElement('canvas')
    canvas.width = size
    canvas.height = size
    const ctx = canvas.getContext('2d')!

    // Dark background
    ctx.fillStyle = '#1e293b'
    ctx.fillRect(0, 0, size, size)

    // Music note icon
    ctx.fillStyle = '#64748b'
    ctx.font = '48px serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText('\u266B', size / 2, size / 2)

    canvas.toBlob((blob) => {
      if (blob) {
        resolve(URL.createObjectURL(blob))
      } else {
        resolve('')
      }
    }, 'image/png')
  })
}

export function useAudioWorkspace() {
  const filesStore = useFilesStore()
  const taskStore = useTaskStore()
  const toast = useToast()
  const { downloadFile, downloadBatch } = useFileDownload()
  const { t } = useI18n()

  // ── Collection (multi-audio state) ──
  const collection = useMediaCollection({
    shouldAddToHistory: (result) => !result.text_content && !result.text_file_id,
  })

  // ── Audio-specific state ──
  const audioInfo = ref<AudioInfo | null>(null)

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

  /** File ID for download: latest result, or original */
  const activeFileId = computed<string | null>(
    () => historyStack.value.at(-1)?.fileId ?? fileId.value,
  )

  /** Text result (for lyrics/transcribe preview) */
  const textResultFileId = ref<string | null>(null)
  const textResultContent = ref<string | null>(null)

  async function loadAudioInfo() {
    const fid = activeFileId.value
    if (!fid) return
    // MIDI files don't have audio info (not real audio)
    const name = currentFileName.value?.toLowerCase() || ''
    if (name.endsWith('.mid') || name.endsWith('.midi')) return
    try {
      const res = await apiFetch(`/audio/info/${fid}`)
      if (res.ok) audioInfo.value = await res.json()
    } catch (e) {
      console.error('Failed to load audio info:', e)
    }
  }

  // Reload audio info when active entry or result file changes
  watch([() => collection.activeId.value, activeFileId], async () => {
    audioInfo.value = null
    if (fileId.value) await loadAudioInfo()
  })

  async function handleFile(file: File, srcDir?: string) {
    // 檢查副檔名
    const ext = ('.' + file.name.split('.').pop()!).toLowerCase()
    if (!AUDIO_EXTS.has(ext)) {
      log.warn('handleFile skipped unsupported format', { fileName: file.name, ext })
      toast.show(`不支援的格式：${ext}`, { type: 'error', icon: 'bi-x-circle' })
      return
    }
    log.info('handleFile', { fileName: file.name, size: file.size, srcDir })
    audioInfo.value = null

    const entryId = await collection.addEntry(file, srcDir, generateAudioThumbnail)

    try {
      const uploadedFileId = await filesStore.uploadFile(file, srcDir)
      log.info('handleFile uploaded', { fileName: file.name, fileId: uploadedFileId })
      collection.updateEntry(entryId, { fileId: uploadedFileId, status: 'idle' })
      await loadAudioInfo()
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

  const { handleExistingFiles, addExistingFile } = useExistingFileHandler(collection, loadAudioInfo)
  usePendingFileListener(handleFile, handleFiles, handleExistingFiles)

  function handleRemoveFile() {
    const id = collection.activeId.value
    if (id) {
      collection.removeEntry(id)
    }
    if (!collection.hasEntries.value) {
      audioInfo.value = null
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

  function handleDownload(outputFormat?: string, suffix = '_output') {
    // Text result download (lyrics/transcribe)
    if (textResultFileId.value) {
      const baseName = currentFileName.value.replace(/\.[^.]+$/, '')
      downloadFile(textResultFileId.value, `${baseName}${suffix}.${outputFormat ?? 'txt'}`, sourceDir.value)
      return
    }
    // Binary result download (from history stack)
    const latest = historyStack.value.at(-1)
    if (!latest) return

    // Multi-file result (e.g. separation stems + optional MIDI)
    const outputFiles = latest.meta?.output_files as { file_id: string; filename: string }[] | undefined
    if (outputFiles && outputFiles.length > 1) {
      const batch = outputFiles.map(f => ({ fileId: f.file_id, filename: f.filename }))
      // Include MIDI file if present
      const midiFileId = latest.meta?.midi_file_id as string | undefined
      const midiFilename = latest.meta?.midi_filename as string | undefined
      if (midiFileId && midiFilename) {
        batch.push({ fileId: midiFileId, filename: midiFilename })
      }
      downloadBatch(batch)
      return
    }

    downloadFile(latest.fileId, latest.outputFilename, sourceDir.value)
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
    async (task) => {
      if (!task || task.status !== 'completed' || !task.result) return
      if (_notifiedTaskIds.has(task.taskId)) return
      _notifiedTaskIds.add(task.taskId)

      const r = task.result as { output_file_id?: string; text_content?: string; text_file_id?: string }

      // Handle text results (lyrics, transcribe)
      if (r.text_content || r.text_file_id) {
        textResultFileId.value = r.text_file_id ?? r.output_file_id ?? null
        textResultContent.value = r.text_content ?? null
        // If we have a file ID but no content, fetch it
        if (!textResultContent.value && textResultFileId.value) {
          try {
            const res = await apiFetch(`/files/${textResultFileId.value}/download`)
            if (res.ok) textResultContent.value = await res.text()
          } catch {}
        }
      }

      log.info('task completed', { taskId: task.taskId, taskType: task.taskType, outputFileId: r.output_file_id })

      toast.show(t('toast.task_completed', { label: task.label ?? '' }), {
        type: 'success',
        icon: 'bi-check-circle',
      })
    },
    { deep: true }
  )

  /** Add a MIDI file (already on backend) to the filmstrip without re-uploading */
  function addMidiEntry(midiFileId: string, midiFilename: string): string {
    return addExistingFile({
      fileId: midiFileId,
      filename: midiFilename,
      fileSize: 0,            // MIDI: not real audio; loadAudioInfo skips .mid/.midi; no consumer reads size
      mimeType: 'audio/midi',
    })
  }

  // Reset text result when switching files
  watch(() => collection.activeId.value, () => {
    textResultFileId.value = null
    textResultContent.value = null
  })

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
    currentTaskId,
    hasResult,
    canGoBack,
    canGoForward,
    audioInfo,
    textResultContent,
    textResultFileId,
    collection,
    handleFile,
    handleFiles,
    handleRemoveFile,
    handlePanelSubmit,
    handleDownload,
    handleDownloadBatch,
    downloadFile,
    addMidiEntry,
    handleExistingFiles,
    goBack,
    goForward,
  }
}
