import { describe, it, expect } from 'vitest'
import { detectMediaKind, MEDIA_KIND_EXTS } from '../mediaKind'
import { detectTypeByName } from '../mediaType'

/**
 * 後端 backend/app/workers/media_kind.py 副檔名表快照(含 .lrc 補項)。
 * 兩側漂移時本測試必紅——改任何一側都要同步另一側(GIF/APNG 三點對齊教訓)。
 */
const BACKEND_TABLE: Record<string, string[]> = {
  image: ['jpg', 'jpeg', 'png', 'apng', 'gif', 'webp', 'bmp', 'tiff', 'tif', 'svg', 'ico', 'avif', 'heic', 'heif'],
  audio: ['mp3', 'wav', 'flac', 'ogg', 'aac', 'm4a', 'wma', 'opus', 'mid', 'midi'],
  video: ['mp4', 'mov', 'webm', 'avi', 'mkv', 'flv', 'wmv', 'm4v'],
  document: ['pdf', 'doc', 'docx', 'txt', 'srt', 'vtt', 'md', 'csv', 'json', 'html', 'odt', 'lrc'],
}

describe('mediaKind mirrors backend media_kind.py', () => {
  it('extension tables match the backend snapshot exactly', () => {
    for (const kind of Object.keys(BACKEND_TABLE)) {
      expect([...MEDIA_KIND_EXTS[kind as keyof typeof MEDIA_KIND_EXTS]].sort())
        .toEqual([...BACKEND_TABLE[kind]].sort())
    }
  })

  it('detectMediaKind classifies by extension', () => {
    expect(detectMediaKind('a.srt')).toBe('document')
    expect(detectMediaKind('b.LRC')).toBe('document')
    expect(detectMediaKind('c.gif')).toBe('image')
    expect(detectMediaKind('d.apng')).toBe('image')
    expect(detectMediaKind('e.opus')).toBe('audio')
    expect(detectMediaKind('f.m4v')).toBe('video')
    expect(detectMediaKind('g.xyz')).toBeNull()
    expect(detectMediaKind('noext')).toBeNull()
  })
})

describe('mediaType extMap gains text/document routing (ToolType unchanged)', () => {
  it('routes subtitle/text outputs to the document tool', () => {
    for (const ext of ['srt', 'vtt', 'md', 'csv', 'json', 'html', 'odt', 'lrc']) {
      expect(detectTypeByName(`x.${ext}`)).toBe('document')
    }
  })
})
