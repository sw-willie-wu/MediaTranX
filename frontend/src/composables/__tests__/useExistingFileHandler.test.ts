import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useExistingFileHandler } from '@/composables/useExistingFileHandler'
import { useFilesStore } from '@/stores/files'
import { useMediaCollection } from '@/composables/useMediaCollection'

type AddExistingArgs = Parameters<ReturnType<typeof useMediaCollection>['addExistingEntry']>[0]

function fakeCollection() {
  const calls: AddExistingArgs[] = []
  const addExistingEntry = vi.fn((a: AddExistingArgs): string => { calls.push(a); return 'entry-' + a.fileId })
  return { calls, addExistingEntry }
}

describe('useExistingFileHandler', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('addExistingFile adds entry, syncs files store, returns entryId', () => {
    const c = fakeCollection()
    const { addExistingFile } = useExistingFileHandler(c)
    const id = addExistingFile({ fileId: 'f1', filename: 'a.png', fileSize: 7, mimeType: 'image/png' })
    expect(id).toBe('entry-f1')
    expect(c.addExistingEntry).toHaveBeenCalledOnce()
    expect(c.calls[0].previewUrl).toContain('/files/f1/download')
    const s = useFilesStore()
    expect(s.currentFile?.id).toBe('f1')        // covers agent click_execute guard
    expect(s.files.get('f1')).toBeTruthy()
  })

  it('handleExistingFiles loops refs then calls loadInfo once', async () => {
    const c = fakeCollection()
    const loadInfo = vi.fn()
    const { handleExistingFiles } = useExistingFileHandler(c, loadInfo)
    await handleExistingFiles([
      { fileId: 'a', filename: 'a.mp4', fileSize: 1, mimeType: 'video/mp4' },
      { fileId: 'b', filename: 'b.mp4', fileSize: 2, mimeType: 'video/mp4' },
    ])
    expect(c.addExistingEntry).toHaveBeenCalledTimes(2)
    expect(loadInfo).toHaveBeenCalledOnce()
  })

  it('addExistingFile works for MIDI-shaped ref (fileSize 0, audio/midi) without fetch', () => {
    const c = fakeCollection()
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const { addExistingFile } = useExistingFileHandler(c)
    const id = addExistingFile({ fileId: 'mid1', filename: 'song.mid', fileSize: 0, mimeType: 'audio/midi' })
    expect(id).toBe('entry-mid1')
    expect(fetchMock).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})
