import { ref, watch } from 'vue'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { useFileDownload } from '@/composables/useFileDownload'
import { apiFetch } from '@/composables/useApi'

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

export function useVideoWorkspace() {
  const filesStore = useFilesStore()
  const taskStore = useTaskStore()
  const toast = useToast()
  const { downloadFile } = useFileDownload()

  const hasFile = ref(false)
  const fileId = ref<string | null>(null)
  const isUploading = ref(false)
  const sourceDir = ref<string | undefined>(undefined)
  const currentFileName = ref('')
  const mediaInfo = ref<VideoMediaInfo | null>(null)
  const currentTaskId = ref<string | null>(null)
  const hasResult = ref(false)

  async function loadMediaInfo() {
    if (!fileId.value) return
    try {
      const response = await apiFetch(`/video/info/${fileId.value}`)
      if (response.ok) mediaInfo.value = await response.json()
    } catch (e) {
      console.error('Failed to load media info:', e)
    }
  }

  async function handleFile(file: File, srcDir?: string) {
    hasFile.value = true
    sourceDir.value = srcDir
    hasResult.value = false
    fileId.value = null
    mediaInfo.value = null
    currentFileName.value = file.name
    isUploading.value = true
    try {
      const id = await filesStore.uploadFile(file, srcDir)
      fileId.value = id
      await loadMediaInfo()
    } catch (e) {
      console.error('File upload failed:', e)
    } finally {
      isUploading.value = false
    }
  }

  function handleRemoveFile() {
    hasFile.value = false
    fileId.value = null
    sourceDir.value = undefined
    currentFileName.value = ''
    mediaInfo.value = null
    currentTaskId.value = null
    hasResult.value = false
    isUploading.value = false
  }

  function handlePanelSubmit(taskId: string) {
    currentTaskId.value = taskId
    hasResult.value = true
  }

  function handleDownload(outputFormat?: string, suffix?: string) {
    const task = currentTaskId.value ? taskStore.tasks.get(currentTaskId.value) : null
    if (!task?.result) return
    const r = task.result as { output_file_id?: string }
    if (!r.output_file_id) return
    const baseName = currentFileName.value.replace(/\.[^.]+$/, '')
    const fmt = outputFormat ?? 'mp4'
    const sfx = suffix ?? '_output'
    downloadFile(r.output_file_id, `${baseName}${sfx}.${fmt}`, sourceDir.value)
  }

  const _notifiedTaskIds = new Set<string>()
  watch(
    () => currentTaskId.value ? taskStore.tasks.get(currentTaskId.value) : null,
    (task) => {
      if (!task || task.status !== 'completed' || !task.result) return
      if (_notifiedTaskIds.has(task.taskId)) return
      _notifiedTaskIds.add(task.taskId)
      const r = task.result as { output_file_id?: string }
      if (!r.output_file_id) return
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
    mediaInfo,
    currentTaskId,
    hasResult,
    handleFile,
    handleRemoveFile,
    handlePanelSubmit,
    handleDownload,
  }
}
