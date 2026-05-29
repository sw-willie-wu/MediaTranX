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
