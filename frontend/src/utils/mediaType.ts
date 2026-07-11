export type ToolType = 'video' | 'audio' | 'image' | 'document'

const mimeTypeMap: Record<string, ToolType> = {
  // 影片
  'video/mp4': 'video',
  'video/webm': 'video',
  'video/avi': 'video',
  'video/quicktime': 'video',
  'video/x-msvideo': 'video',
  'video/x-matroska': 'video',
  // 音訊
  'audio/mpeg': 'audio',
  'audio/mp3': 'audio',
  'audio/wav': 'audio',
  'audio/ogg': 'audio',
  'audio/flac': 'audio',
  'audio/aac': 'audio',
  'audio/x-m4a': 'audio',
  'audio/midi': 'audio',
  'audio/x-midi': 'audio',
  // 圖片
  'image/jpeg': 'image',
  'image/png': 'image',
  'image/gif': 'image',
  'image/apng': 'image',
  'image/webp': 'image',
  'image/bmp': 'image',
  'image/tiff': 'image',
  // 文件
  'application/pdf': 'document',
  'application/msword': 'document',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'document',
}

const extMap: Record<string, ToolType> = {
  // 影片
  mp4: 'video', mkv: 'video', avi: 'video', mov: 'video', webm: 'video', wmv: 'video', flv: 'video',
  // 音訊
  mp3: 'audio', wav: 'audio', flac: 'audio', aac: 'audio', ogg: 'audio', m4a: 'audio', wma: 'audio', mid: 'audio', midi: 'audio',
  // 圖片
  jpg: 'image', jpeg: 'image', png: 'image', apng: 'image', gif: 'image', webp: 'image', bmp: 'image', tiff: 'image', ico: 'image',
  // 文件（srt/vtt/md/... 為字幕與文字產出的路由補項——只加映射、不動 ToolType 值）
  pdf: 'document', doc: 'document', docx: 'document', txt: 'document',
  srt: 'document', vtt: 'document', md: 'document', csv: 'document',
  json: 'document', html: 'document', odt: 'document', lrc: 'document',
}

export function detectMediaType(file: File): ToolType | null {
  return detectTypeByName(file.name, file.type)
}

/**
 * Detect media type from a filename + optional mime type — same logic as
 * detectMediaType but without needing a File instance. Useful for backend-
 * sourced metadata (Results drawer entries) where we only have strings.
 */
export function detectTypeByName(filename: string, mimeType?: string): ToolType | null {
  if (mimeType && mimeTypeMap[mimeType]) return mimeTypeMap[mimeType]
  if (mimeType?.startsWith('video/')) return 'video'
  if (mimeType?.startsWith('audio/')) return 'audio'
  if (mimeType?.startsWith('image/')) return 'image'
  const ext = filename.split('.').pop()?.toLowerCase()
  if (ext && extMap[ext]) return extMap[ext]
  return null
}

const toolLabels: Record<ToolType, string> = {
  video: '影片工具',
  audio: '音訊工具',
  image: '圖片工具',
  document: '文件工具',
}

const toolPaths: Record<ToolType, string> = {
  video: '/video',
  audio: '/audio',
  image: '/image',
  document: '/document',
}

export function getToolLabel(type: ToolType): string {
  return toolLabels[type]
}

export function getToolPath(type: ToolType): string {
  return toolPaths[type]
}
