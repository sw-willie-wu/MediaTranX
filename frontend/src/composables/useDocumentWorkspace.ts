import { ref, watch } from 'vue'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { useFileDownload } from '@/composables/useFileDownload'
import { apiFetch } from '@/composables/useApi'

export function useDocumentWorkspace() {
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

  // OCR 文字結果（供 modal 顯示）
  const textResultFileId   = ref<string | null>(null)
  const textResultFilename = ref<string | null>(null)
  const textResultContent  = ref<string | null>(null)

  async function handleFile(file: File, srcDir?: string) {
    hasFile.value = true
    sourceDir.value = srcDir
    currentFileName.value = file.name
    hasResult.value = false
    fileId.value = null
    isUploading.value = true
    textResultContent.value = null
    textResultFileId.value = null
    textResultFilename.value = null
    try {
      fileId.value = await filesStore.uploadFile(file, srcDir)
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
    textResultContent.value = null
    textResultFileId.value = null
    textResultFilename.value = null
  }

  function handlePanelSubmit(taskId: string) {
    currentTaskId.value = taskId
  }

  function handleDownload(fallbackSuffix = '_output', fallbackExt = 'pdf') {
    const task = currentTaskId.value ? taskStore.tasks.get(currentTaskId.value) : null
    if (!task?.result) return
    const r = task.result as { output_file_id?: string; output_filename?: string }
    if (!r.output_file_id) return
    const name = r.output_filename
      ?? `${currentFileName.value.replace(/\.[^.]+$/, '')}${fallbackSuffix}.${fallbackExt}`
    downloadFile(r.output_file_id, name, sourceDir.value)
  }

  function handleTextDownload() {
    if (!textResultFileId.value || !textResultFilename.value) return
    downloadFile(textResultFileId.value, textResultFilename.value, sourceDir.value)
  }

  const _notifiedTaskIds = new Set<string>()
  watch(
    () => currentTaskId.value ? taskStore.tasks.get(currentTaskId.value) : null,
    async (task) => {
      if (!task || task.status !== 'completed' || !task.result) return
      if (_notifiedTaskIds.has(task.taskId)) return
      _notifiedTaskIds.add(task.taskId)
      const r = task.result as { output_file_id?: string; output_filename?: string }
      if (!r.output_file_id) return
      hasResult.value = true

      // OCR 任務：額外載入文字內容供 modal 顯示
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

      toast.show(`${task.label ?? '處理'} 完成`, {
        type: 'success',
        icon: 'bi-check-circle',
        action: { label: '下載', callback: () => handleDownload() },
      })
    },
    { deep: true },
  )

  return {
    hasFile,
    fileId,
    isUploading,
    sourceDir,
    currentFileName,
    currentTaskId,
    hasResult,
    textResultFileId,
    textResultFilename,
    textResultContent,
    handleFile,
    handleRemoveFile,
    handlePanelSubmit,
    handleDownload,
    handleTextDownload,
  }
}
