/**
 * 五官媒體歸類(pipeline/results 用)——與後端 backend/app/workers/media_kind.py
 * 完全鏡像,由 __tests__/mediaKind.test.ts 的後端表快照釘住。
 * 注意:這與 mediaType.ts 的 ToolType(4 視圖路由)是兩套分類學,不要混用。
 */
export type MediaKindT = 'video' | 'audio' | 'image' | 'document'

export const MEDIA_KIND_EXTS: Record<MediaKindT, Set<string>> = {
  image: new Set(['jpg', 'jpeg', 'png', 'apng', 'gif', 'webp', 'bmp', 'tiff', 'tif', 'svg', 'ico', 'avif', 'heic', 'heif']),
  audio: new Set(['mp3', 'wav', 'flac', 'ogg', 'aac', 'm4a', 'wma', 'opus', 'mid', 'midi']),
  video: new Set(['mp4', 'mov', 'webm', 'avi', 'mkv', 'flv', 'wmv', 'm4v']),
  document: new Set(['pdf', 'doc', 'docx', 'txt', 'srt', 'vtt', 'md', 'csv', 'json', 'html', 'odt', 'lrc']),
}

export function detectMediaKind(filename: string): MediaKindT | null {
  const dot = filename.lastIndexOf('.')
  if (dot < 0 || dot === filename.length - 1) return null
  const ext = filename.slice(dot + 1).toLowerCase()
  for (const kind of Object.keys(MEDIA_KIND_EXTS) as MediaKindT[]) {
    if (MEDIA_KIND_EXTS[kind].has(ext)) return kind
  }
  return null
}
