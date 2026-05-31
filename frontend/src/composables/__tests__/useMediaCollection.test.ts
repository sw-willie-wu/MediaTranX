import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useMediaCollection } from '@/composables/useMediaCollection'

function makeFile(name = 'a.png', type = 'image/png', size = 1234) {
  // jsdom File: size derived from parts; pad to requested size
  return new File([new Uint8Array(size)], name, { type })
}

describe('useMediaCollection — addEntry populates fileName/fileSize', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('addEntry sets fileName and fileSize from the File', async () => {
    const c = useMediaCollection()
    const id = await c.addEntry(makeFile('photo.jpg', 'image/jpeg', 4096))
    const entry = c.entries.value.get(id)!
    expect(entry.fileName).toBe('photo.jpg')
    expect(entry.fileSize).toBe(4096)
    expect(entry.file).not.toBeNull()
  })
})

describe('useMediaCollection — addExistingEntry', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('creates an entry with file=null, fileId set, idle, url preview', () => {
    const c = useMediaCollection()
    const url = 'http://localhost:8001/api/files/abc/download'
    const id = c.addExistingEntry({
      fileId: 'abc', fileName: 'out.mp4', fileSize: 999, mimeType: 'video/mp4', previewUrl: url,
    })
    const e = c.entries.value.get(id)!
    expect(e.file).toBeNull()
    expect(e.fileId).toBe('abc')
    expect(e.fileName).toBe('out.mp4')
    expect(e.fileSize).toBe(999)
    expect(e.status).toBe('idle')
    expect(e.previewUrl).toBe(url)
    expect(e.thumbnailUrl).toBe(url)
    expect(c.activeId.value).toBe(id)
  })

  it('removeEntry on an adopted entry does NOT revoke the http previewUrl', () => {
    const c = useMediaCollection()
    const spy = vi.spyOn(URL, 'revokeObjectURL')
    const id = c.addExistingEntry({
      fileId: 'x', fileName: 'a.png', fileSize: 1, mimeType: 'image/png',
      previewUrl: 'http://localhost:8001/api/files/x/download',
    })
    c.removeEntry(id)
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })

  it('adopted entry is NOT picked up by the task-completion watcher (no registerTask)', async () => {
    const c = useMediaCollection()
    const id = c.addExistingEntry({
      fileId: 'y', fileName: 'b.mp4', fileSize: 2, mimeType: 'video/mp4',
      previewUrl: 'http://localhost:8001/api/files/y/download',
    })
    // No registerTask called → taskEntryMap has no mapping → watcher ignores it.
    // Entry stays 'idle' with empty historyStack regardless of task store activity.
    const e = c.entries.value.get(id)!
    expect(e.status).toBe('idle')
    expect(e.historyStack).toHaveLength(0)
    expect(e.currentTaskId).toBeNull()
  })
})
