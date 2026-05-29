import { describe, it, expect, beforeEach } from 'vitest'
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
