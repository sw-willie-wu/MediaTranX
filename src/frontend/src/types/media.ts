/**
 * 媒體檔案相關類型定義
 */

export type MediaType = 'image' | 'video' | 'audio' | 'subtitle' | 'unknown'

export interface MediaFile {
  id: string
  name: string
  originalName: string
  path: string
  size: number
  mimeType: string
  type: MediaType
  createdAt: Date
  metadata?: MediaMetadata
  previewUrl?: string
}

export interface MediaMetadata {
  duration?: number
  width?: number
  height?: number
  codec?: string
  bitrate?: number
  fps?: number
  channels?: number
  sampleRate?: number
}

export interface FileUploadResponse {
  file_id: string
  filename: string
  file_size: number
  mime_type: string
}
