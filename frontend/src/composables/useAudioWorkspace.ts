import { ref, computed, watch } from 'vue'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { useFileDownload } from '@/composables/useFileDownload'
import { useMediaCollection } from '@/composables/useMediaCollection'
import { apiFetch } from '@/composables/useApi'
import { createLogger } from '@/utils/logger'

const log = createLogger('AudioWorkspace')

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
  const { downloadFile } = useFileDownload()

  // ── Collection (multi-audio state) ──
  const collection = useMediaCollection()

  // ── Audio-specific state ──
  const audioInfo = ref<AudioInfo | null>(null)

  // ── Derived from active entry ──
  const hasFile = computed(() => collection.hasEntries.value)
  const fileId = computed<string | null>(() => collection.activeEntry.value?.fileId ?? null)
  const isUploading = computed<boolean>(() => collection.activeEntry.value?.status === 'uploading')
  const sourceDir = computed<string | undefined>(() => collection.activeEntry.value?.sourceDir)
  const currentFileName = computed<string>(() => collection.activeEntry.value?.file.name ?? '')
  const currentTaskId = computed<string | null>(() => collection.activeEntry.value?.currentTaskId ?? null)
  const hasResult = computed<boolean>(() => {
    const entry = collection.activeEntry.value
    if (!entry?.currentTaskId) return false
    const task = taskStore.tasks.get(entry.currentTaskId)
    return task?.status === 'completed' && !!task.result
  })

  async function loadAudioInfo() {
    if (!fileId.value) return
    try {
      const res = await apiFetch(`/audio/info/${fileId.value}`)
      if (res.ok) audioInfo.value = await res.json()
    } catch (e) {
      console.error('Failed to load audio info:', e)
    }
  }

  // Reload audio info when active entry changes
  watch(() => collection.activeId.value, async () => {
    audioInfo.value = null
    if (fileId.value) await loadAudioInfo()
  })

  async function handleFile(file: File, srcDir?: string) {
    log.info('handleFile', { fileName: file.name, size: file.size, srcDir })
    audioInfo.value = null

    const entryId = await collection.addEntry(file, srcDir, generateAudioThumbnail)

    try {
      const uploadedFileId = await filesStore.uploadFile(file, srcDir)
      log.info('handleFile uploaded', { fileName: file.name, fileId: uploadedFileId })
      collection.updateEntry(entryId, { fileId: uploadedFileId, status: 'idle' })
      await loadAudioInfo()
    } catch (e: any) {
      log.error('handleFile upload failed', { fileName: file.name, error: e.message })
      collection.updateEntry(entryId, { status: 'idle' })
      toast.show(e.message || '上傳失敗', { type: 'error', icon: 'bi-x-circle' })
    }
  }

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
      audioInfo.value = null
    }
  }

  function handlePanelSubmit(taskId: string) {
    log.info('handlePanelSubmit', { taskId })
    const entry = collection.activeEntry.value
    if (entry) {
      collection.updateEntry(entry.id, { currentTaskId: taskId, status: 'processing' })
    }
  }

  function handleDownload(outputFormat?: string, suffix = '_output') {
    const task = currentTaskId.value ? taskStore.tasks.get(currentTaskId.value) : null
    if (!task?.result) return
    const r = task.result as { output_file_id?: string }
    if (!r.output_file_id) return
    const baseName = currentFileName.value.replace(/\.[^.]+$/, '')
    downloadFile(r.output_file_id, `${baseName}${suffix}.${outputFormat ?? 'mp3'}`, sourceDir.value)
  }

  // Watch for task completion
  const _notifiedTaskIds = new Set<string>()
  watch(
    () => currentTaskId.value ? taskStore.tasks.get(currentTaskId.value) : null,
    (task) => {
      if (!task || task.status !== 'completed' || !task.result) return
      if (_notifiedTaskIds.has(task.taskId)) return
      _notifiedTaskIds.add(task.taskId)

      const entry = collection.activeEntry.value
      if (entry) {
        collection.updateEntry(entry.id, { status: 'done' })
      }

      const r = task.result as { output_file_id?: string }
      if (!r.output_file_id) return
      log.info('task completed', { taskId: task.taskId, taskType: task.taskType, outputFileId: r.output_file_id })
      toast.show(`${task.label ?? '處理'} 完成`, {
        type: 'success',
        icon: 'bi-check-circle',
        action: { label: '下載', callback: () => handleDownload() },
      })
    },
    { deep: true }
  )

  return {
    hasFile,
    fileId,
    isUploading,
    sourceDir,
    currentFileName,
    currentTaskId,
    hasResult,
    audioInfo,
    collection,
    handleFile,
    handleFiles,
    handleRemoveFile,
    handlePanelSubmit,
    handleDownload,
  }
}
