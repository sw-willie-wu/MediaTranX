import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useFilesStore } from '@/stores/files'

describe('files store — pending-result channel + adoptResultFile', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('setPendingResults then consumePendingResults returns refs and clears', () => {
    const s = useFilesStore()
    const refs = [{ fileId: 'a', filename: 'a.mp4', fileSize: 10, mimeType: 'video/mp4' }]
    s.setPendingResults(refs)
    expect(s.consumePendingResults()).toEqual(refs)
    expect(s.consumePendingResults()).toEqual([])
  })

  it('queueVideoDownload accumulates; consumeVideoDownloads drains and clears (separate from pendingResults)', () => {
    const s = useFilesStore()
    const a = { fileId: 'a', filename: 'a.mp4', fileSize: 10, mimeType: 'video/mp4' }
    const b = { fileId: 'b', filename: 'b.mp4', fileSize: 20, mimeType: 'video/mp4' }
    s.queueVideoDownload(a)
    s.queueVideoDownload(b)
    // does NOT leak into the generic pending-results channel
    expect(s.consumePendingResults()).toEqual([])
    expect(s.consumeVideoDownloads()).toEqual([a, b])
    expect(s.consumeVideoDownloads()).toEqual([])
  })

  it('adoptResultFile registers a MediaFile + sets currentFile + returns it with download previewUrl', () => {
    const s = useFilesStore()
    const mf = s.adoptResultFile({ fileId: 'fid', filename: 'r.png', fileSize: 5, mimeType: 'image/png' })
    expect(mf.id).toBe('fid')
    expect(mf.type).toBe('image')
    expect(mf.size).toBe(5)
    expect(mf.previewUrl).toContain('/files/fid/download')
    expect(s.files.get('fid')).toEqual(mf)
    expect(s.currentFile?.id).toBe('fid')
  })
})
