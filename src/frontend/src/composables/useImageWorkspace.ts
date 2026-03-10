import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useFilesStore } from '@/stores/files'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { useFileDownload } from '@/composables/useFileDownload'
import { apiFetch, getApiBase } from '@/composables/useApi'

export interface ImageInfo {
  width: number
  height: number
  format: string
  mode: string
  file_size: number
}

export function useImageWorkspace() {
  const router = useRouter()
  const filesStore = useFilesStore()
  const taskStore = useTaskStore()
  const toast = useToast()
  const { downloadFile } = useFileDownload()

  const hasFile = ref(false)
  const fileId = ref<string | null>(null)
  const isUploading = ref(false)
  const sourceDir = ref<string | undefined>(undefined)
  const currentFileName = ref('')
  const imageInfo = ref<ImageInfo | null>(null)
  const isLoadingInfo = ref(false)
  const currentTaskId = ref<string | null>(null)
  const aiEnvReady = ref(false)

  // 文字輸出結果（OCR 等非圖片任務）
  const textResultFileId = ref<string | null>(null)
  const textResultFilename = ref<string | null>(null)
  const textResultContent = ref<string | null>(null)

  // 歷史堆疊（支援連續處理）
  interface HistoryEntry { fileId: string; previewUrl: string; outputFilename: string }
  const historyStack = ref<HistoryEntry[]>([])

  const canGoBack = computed(() => historyStack.value.length > 0)
  const activeFileId = computed(() => historyStack.value.at(-1)?.fileId ?? fileId.value)
  const activePreviewUrl = computed(() => historyStack.value.at(-1)?.previewUrl ?? null)
  const hasResult = computed(() => canGoBack.value || !!textResultFileId.value)

  function goBack() {
    historyStack.value.pop()
    loadImageInfo()
  }

  async function checkAiEnvironment(currentFunction?: string) {
    try {
      const res = await apiFetch('/setup/status')
      const status = await res.json()
      aiEnvReady.value = status.ai_env_ready
      if (!aiEnvReady.value && (currentFunction === 'upscale')) {
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

  async function handleFile(file: File, srcDir?: string) {
    hasFile.value = true
    sourceDir.value = srcDir
    currentFileName.value = file.name
    imageInfo.value = null
    historyStack.value = []
    currentTaskId.value = null
    textResultFileId.value = null
    textResultFilename.value = null
    textResultContent.value = null
    isUploading.value = true
    try {
      fileId.value = await filesStore.uploadFile(file, srcDir)
      await loadImageInfo()
    } catch (e: any) {
      toast.show(e.message || '上傳失敗', { type: 'error', icon: 'bi-x-circle' })
    } finally {
      isUploading.value = false
    }
  }

  function handleRemoveFile() {
    hasFile.value = false
    fileId.value = null
    sourceDir.value = undefined
    currentFileName.value = ''
    imageInfo.value = null
    historyStack.value = []
    currentTaskId.value = null
    textResultFileId.value = null
    textResultFilename.value = null
    textResultContent.value = null
    isUploading.value = false
    isLoadingInfo.value = false
  }

  function handlePanelSubmit(taskId: string) {
    currentTaskId.value = taskId
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

  watch(
    () => currentTaskId.value ? taskStore.tasks.get(currentTaskId.value) : null,
    (task) => {
      if (!task) return
      if (task.status === 'completed' && task.result) {
        const r = task.result as { output_file_id?: string; output_filename?: string }
        if (r.output_file_id) {
          const isText = /\.(txt|md|json|csv|srt|vtt)$/i.test(r.output_filename ?? '')
          if (isText) {
            // 文字輸出：不更新圖片預覽，儲存下載資訊並 fetch 內容供預覽
            textResultFileId.value = r.output_file_id
            textResultFilename.value = r.output_filename ?? `${currentFileName.value.replace(/\.[^.]+$/, '')}_ocr.txt`
            // 非同步 fetch 文字內容
            apiFetch(`/files/${r.output_file_id}/download`)
              .then(res => res.ok ? res.text() : null)
              .then(text => { textResultContent.value = text })
              .catch(() => {})
            toast.show(`${task.label ?? '處理'} 完成`, {
              type: 'success',
              icon: 'bi-check-circle',
              action: { label: '下載', callback: () => handleTextDownload() },
            })
          } else {
            // 圖片輸出：推入歷史堆疊
            const url = `${getApiBase()}/files/${r.output_file_id}/download`
            historyStack.value.push({
              fileId: r.output_file_id,
              previewUrl: url,
              outputFilename: r.output_filename ?? `${currentFileName.value.replace(/\.[^.]+$/, '')}_result`,
            })
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
    { deep: true }
  )

  return {
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
    goBack,
    checkAiEnvironment,
    loadImageInfo,
    handleFile,
    handleRemoveFile,
    handlePanelSubmit,
    handleDownload,
    handleTextDownload,
    textResultFileId,
    textResultFilename,
    textResultContent,
  }
}
