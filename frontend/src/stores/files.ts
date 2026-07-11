/**
 * 檔案狀態管理
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { MediaFile, MediaType, FileUploadResponse } from '@/types/media'

import { getApiBase } from '@/composables/useApi'
import { createLogger } from '@/utils/logger'

const log = createLogger('FilesStore')

export interface PendingResultRef {
  fileId: string
  filename: string
  fileSize: number
  mimeType: string
}

export const useFilesStore = defineStore('files', () => {
  // 狀態
  const files = ref<Map<string, MediaFile>>(new Map())
  const currentFile = ref<MediaFile | null>(null)
  const isUploading = ref(false)
  const uploadProgress = ref(0)

  // 暫存從首頁拖曳過來的檔案（跨頁面傳遞用）
  const pendingFile = ref<File | null>(null)
  const pendingSourceDir = ref<string | undefined>(undefined)

  // 批次暫存（跨工具開啟多選結果用）
  const pendingFiles = ref<File[]>([])

  // 暫存「以既有 file_id 引用」的 result（加入工具用，不搬 bytes）
  const pendingResults = ref<PendingResultRef[]>([])

  // 計算屬性
  const allFiles = computed(() => Array.from(files.value.values()))

  const imageFiles = computed(() =>
    allFiles.value.filter((f) => f.type === 'image')
  )

  const videoFiles = computed(() =>
    allFiles.value.filter((f) => f.type === 'video')
  )

  const audioFiles = computed(() =>
    allFiles.value.filter((f) => f.type === 'audio')
  )

  // 上傳檔案（sourceDir 由呼叫端提供，從原始 File.path 提取）
  // 當 sourceDir 存在時（Electron 環境），直接註冊本機路徑，避免大檔案複製
  async function uploadFile(file: File, sourceDir?: string): Promise<string> {
    isUploading.value = true
    uploadProgress.value = 0
    log.info('uploadFile', { fileName: file.name, size: file.size, mode: sourceDir ? 'register' : 'upload' })

    try {
      let data: FileUploadResponse

      if (sourceDir) {
        // Electron 環境：直接註冊本機檔案路徑，不需複製
        const filePath = sourceDir.replace(/\\/g, '/') + '/' + file.name
        const response = await fetch(`${getApiBase()}/files/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ file_path: filePath }),
        })

        if (!response.ok) {
          throw new Error(`Register failed: ${response.statusText}`)
        }

        data = await response.json()
      } else {
        // 瀏覽器環境：透過 HTTP 上傳
        const formData = new FormData()
        formData.append('file', file)

        const response = await fetch(`${getApiBase()}/files/upload`, {
          method: 'POST',
          body: formData,
        })

        if (!response.ok) {
          throw new Error(`Upload failed: ${response.statusText}`)
        }

        data = await response.json()
      }

      // 建立本地檔案記錄
      const mediaFile: MediaFile = {
        id: data.file_id,
        name: data.filename,
        originalName: file.name,
        path: '',
        size: data.file_size,
        mimeType: data.mime_type,
        type: getMediaType(data.mime_type),
        createdAt: new Date(),
        previewUrl: URL.createObjectURL(file),
      }

      files.value.set(data.file_id, mediaFile)
      currentFile.value = mediaFile
      log.info('uploadFile done', { fileId: data.file_id, mimeType: data.mime_type })

      return data.file_id
    } finally {
      isUploading.value = false
      uploadProgress.value = 0
    }
  }

  /** Electron 原生資料夾選取:以路徑零搬運註冊本機檔,回 PendingResultRef。 */
  async function registerLocalFile(filePath: string): Promise<PendingResultRef> {
    const res = await fetch(`${getApiBase()}/files/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath }),
    })
    if (!res.ok) throw new Error(`register failed: ${res.status}`)
    const d = await res.json()
    return { fileId: d.file_id, filename: d.filename, fileSize: d.file_size, mimeType: d.mime_type }
  }

  // 取得媒體類型
  function getMediaType(mimeType: string): MediaType {
    if (mimeType.startsWith('image/')) return 'image'
    if (mimeType.startsWith('video/')) return 'video'
    if (mimeType.startsWith('audio/')) return 'audio'
    if (
      mimeType.includes('subtitle') ||
      mimeType.includes('srt') ||
      mimeType.includes('ass') ||
      mimeType.includes('vtt')
    ) {
      return 'subtitle'
    }
    return 'unknown'
  }

  // 取得檔案資訊
  async function getFileInfo(fileId: string): Promise<MediaFile | null> {
    const cached = files.value.get(fileId)
    if (cached) return cached

    try {
      const response = await fetch(`${getApiBase()}/files/${fileId}`)
      if (!response.ok) return null

      const data = await response.json()
      const mediaFile: MediaFile = {
        id: data.file_id,
        name: data.filename,
        originalName: data.original_filename,
        path: data.file_path,
        size: data.file_size,
        mimeType: data.mime_type,
        type: getMediaType(data.mime_type),
        createdAt: new Date(data.created_at),
        metadata: data.metadata,
      }

      files.value.set(fileId, mediaFile)
      return mediaFile
    } catch (error) {
      console.error('Failed to get file info:', error)
      return null
    }
  }

  // 下載檔案
  async function downloadFile(fileId: string): Promise<void> {
    const file = files.value.get(fileId)
    const filename = file?.originalName || 'download'

    const response = await fetch(`${getApiBase()}/files/${fileId}/download`)
    if (!response.ok) {
      throw new Error('Download failed')
    }

    const blob = await response.blob()
    const url = URL.createObjectURL(blob)

    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)

    URL.revokeObjectURL(url)
  }

  // 刪除檔案
  async function deleteFile(fileId: string): Promise<boolean> {
    log.info('deleteFile', { fileId })
    try {
      const response = await fetch(`${getApiBase()}/files/${fileId}`, {
        method: 'DELETE',
      })

      if (response.ok) {
        const file = files.value.get(fileId)
        if (file?.previewUrl) {
          URL.revokeObjectURL(file.previewUrl)
        }
        files.value.delete(fileId)

        if (currentFile.value?.id === fileId) {
          currentFile.value = null
        }

        return true
      }
    } catch (error) {
      console.error('Failed to delete file:', error)
    }
    return false
  }

  // 設定當前檔案
  function setCurrentFile(fileId: string | null) {
    if (fileId === null) {
      currentFile.value = null
    } else {
      currentFile.value = files.value.get(fileId) || null
    }
  }

  // 清理預覽 URL
  function cleanup() {
    for (const file of files.value.values()) {
      if (file.previewUrl) {
        URL.revokeObjectURL(file.previewUrl)
      }
    }
    files.value.clear()
    currentFile.value = null
  }

  // 設定暫存檔案（由 HomeView 等入口呼叫，跨頁面傳遞）
  function setPendingFile(file: File, sourceDir?: string) {
    pendingFile.value = file
    pendingSourceDir.value = sourceDir
  }

  // 取出暫存檔案（取出後清除）
  function consumePendingFile(): { file: File; sourceDir?: string } | null {
    const file = pendingFile.value
    const srcDir = pendingSourceDir.value
    pendingFile.value = null
    pendingSourceDir.value = undefined
    if (!file) return null
    return { file, sourceDir: srcDir }
  }

  // 批次暫存檔案（由 results store openManyInTool 呼叫）
  function setPendingFiles(files: File[]) {
    pendingFiles.value = [...files]
  }

  // 取出批次暫存檔案（取出後清除）
  function consumePendingFiles(): File[] {
    const arr = pendingFiles.value
    pendingFiles.value = []
    return arr
  }

  function setPendingResults(refs: PendingResultRef[]) {
    pendingResults.value = [...refs]
  }

  function consumePendingResults(): PendingResultRef[] {
    const arr = pendingResults.value
    pendingResults.value = []
    return arr
  }

  // Video-download-specific queue: completed URL downloads are staged here and
  // adopted ONLY by the Video tool (on activation). Kept separate from the
  // generic pendingResults so no other active tool can consume a video file.
  const pendingVideoDownloads = ref<PendingResultRef[]>([])
  function queueVideoDownload(ref: PendingResultRef) {
    pendingVideoDownloads.value = [...pendingVideoDownloads.value, ref]
  }
  function consumeVideoDownloads(): PendingResultRef[] {
    const arr = pendingVideoDownloads.value
    pendingVideoDownloads.value = []
    return arr
  }

  /** Adopt a backend-resident result file by reference: build a MediaFile,
   *  register it, set as current — no download/upload. */
  function adoptResultFile(ref: PendingResultRef): MediaFile {
    const previewUrl = `${getApiBase()}/files/${ref.fileId}/download`
    const mediaFile: MediaFile = {
      id: ref.fileId,
      name: ref.filename,
      originalName: ref.filename,
      path: '',
      size: ref.fileSize,
      mimeType: ref.mimeType,
      type: getMediaType(ref.mimeType),
      createdAt: new Date(),
      previewUrl,
    }
    files.value.set(ref.fileId, mediaFile)
    currentFile.value = mediaFile
    return mediaFile
  }

  return {
    // 狀態
    files,
    currentFile,
    isUploading,
    uploadProgress,
    pendingFile,
    pendingSourceDir,
    pendingFiles,
    pendingResults,
    pendingVideoDownloads,
    allFiles,
    imageFiles,
    videoFiles,
    audioFiles,
    // 方法
    uploadFile,
    registerLocalFile,
    getFileInfo,
    downloadFile,
    deleteFile,
    setCurrentFile,
    setPendingFile,
    consumePendingFile,
    setPendingFiles,
    consumePendingFiles,
    setPendingResults,
    consumePendingResults,
    queueVideoDownload,
    consumeVideoDownloads,
    adoptResultFile,
    cleanup,
  }
})
