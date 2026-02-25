/**
 * 檔案狀態管理
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { MediaFile, MediaType, FileUploadResponse } from '@/types/media'

const API_BASE = '/api'

export const useFilesStore = defineStore('files', () => {
  // 狀態
  const files = ref<Map<string, MediaFile>>(new Map())
  const currentFile = ref<MediaFile | null>(null)
  const isUploading = ref(false)
  const uploadProgress = ref(0)

  // 暫存從首頁拖曳過來的檔案（跨頁面傳遞用）
  const pendingFile = ref<File | null>(null)
  const pendingSourceDir = ref<string | undefined>(undefined)

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

    try {
      let data: FileUploadResponse

      if (sourceDir) {
        // Electron 環境：直接註冊本機檔案路徑，不需複製
        const filePath = sourceDir.replace(/\\/g, '/') + '/' + file.name
        const response = await fetch(`${API_BASE}/files/register`, {
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

        const response = await fetch(`${API_BASE}/files/upload`, {
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

      return data.file_id
    } finally {
      isUploading.value = false
      uploadProgress.value = 0
    }
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
      const response = await fetch(`${API_BASE}/files/${fileId}`)
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

    const response = await fetch(`${API_BASE}/files/${fileId}/download`)
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
    try {
      const response = await fetch(`${API_BASE}/files/${fileId}`, {
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

  // 取出暫存檔案（取出後清除）
  function consumePendingFile(): { file: File; sourceDir?: string } | null {
    const file = pendingFile.value
    const srcDir = pendingSourceDir.value
    pendingFile.value = null
    pendingSourceDir.value = undefined
    if (!file) return null
    return { file, sourceDir: srcDir }
  }

  return {
    // 狀態
    files,
    currentFile,
    isUploading,
    uploadProgress,
    pendingFile,
    pendingSourceDir,
    allFiles,
    imageFiles,
    videoFiles,
    audioFiles,
    // 方法
    uploadFile,
    getFileInfo,
    downloadFile,
    deleteFile,
    setCurrentFile,
    consumePendingFile,
    cleanup,
  }
})
