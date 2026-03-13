import { ref, watch } from 'vue'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { useFileDownload } from '@/composables/useFileDownload'
import { apiFetch } from '@/composables/useApi'

export interface AudioInfo {
  duration: number
  sample_rate: number
  channels: number
  codec: string
  bitrate: number
  file_size: number
}

export function useAudioWorkspace() {
  const filesStore = useFilesStore()
  const taskStore = useTaskStore()
  const toast = useToast()
  const { downloadFile } = useFileDownload()

  const hasFile = ref(false)
  const fileId = ref<string | null>(null)
  const isUploading = ref(false)
  const sourceDir = ref<string | undefined>(undefined)
  const currentFileName = ref('')
  const currentTaskId = ref<string | null>(null)
  const hasResult = ref(false)
  const audioInfo = ref<AudioInfo | null>(null)

  async function loadAudioInfo() {
    if (!fileId.value) return
    try {
      const res = await apiFetch(`/audio/info/${fileId.value}`)
      if (res.ok) audioInfo.value = await res.json()
    } catch (e) {
      console.error('Failed to load audio info:', e)
    }
  }

  async function handleFile(file: File, srcDir?: string) {
    hasFile.value = true
    sourceDir.value = srcDir
    currentFileName.value = file.name
    hasResult.value = false
    fileId.value = null
    isUploading.value = true
    audioInfo.value = null
    try {
      fileId.value = await filesStore.uploadFile(file, srcDir)
      await loadAudioInfo()
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
    currentTaskId.value = null
    hasResult.value = false
    isUploading.value = false
    audioInfo.value = null
  }

  function handlePanelSubmit(taskId: string) {
    currentTaskId.value = taskId
    hasResult.value = true
  }

  function handleDownload(outputFormat?: string, suffix = '_output') {
    const task = currentTaskId.value ? taskStore.tasks.get(currentTaskId.value) : null
    if (!task?.result) return
    const r = task.result as { output_file_id?: string }
    if (!r.output_file_id) return
    const baseName = currentFileName.value.replace(/\.[^.]+$/, '')
    downloadFile(r.output_file_id, `${baseName}${suffix}.${outputFormat ?? 'mp3'}`, sourceDir.value)
  }

  watch(
    () => currentTaskId.value ? taskStore.tasks.get(currentTaskId.value) : null,
    (task) => {
      if (!task || task.status !== 'completed' || !task.result) return
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
    currentTaskId,
    hasResult,
    audioInfo,
    handleFile,
    handleRemoveFile,
    handlePanelSubmit,
    handleDownload,
  }
}
