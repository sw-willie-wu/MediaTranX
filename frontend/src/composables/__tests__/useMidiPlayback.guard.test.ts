import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// Tone transport stub must cover everything play()->scheduleAllNotes() touches,
// or the "proceeds" case throws after init.
const fakeTransport = {
  bpm: { value: 0 },
  loop: false,
  loopStart: 0,
  loopEnd: 0,
  seconds: 0,
  start: vi.fn(),
  pause: vi.fn(),
  stop: vi.fn(),
  cancel: vi.fn(),
  schedule: vi.fn(),
}
vi.mock('tone', () => ({
  getTransport: () => fakeTransport,
}))
const initSpy = vi.fn()
vi.mock('@/composables/useToneSynth', () => ({
  useToneSynth: () => ({ init: initSpy, allNotesOff: vi.fn(), loadTrackSampler: vi.fn() }),
}))
const guardSpy = vi.fn()
vi.mock('@/composables/useModelGuard', () => ({
  useModelGuard: () => ({ guardModelReady: guardSpy }),
}))

import { useMidiPlayback } from '@/composables/useMidiPlayback'
import { useModelStore } from '@/stores/models'

describe('useMidiPlayback play() guard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    initSpy.mockClear(); guardSpy.mockClear()
  })

  it('aborts play when soundfont not downloaded', async () => {
    const store = useModelStore()
    store.models = [{ id: 'soundfont-musyngkite', downloaded: false } as any]
    store.loaded = true
    guardSpy.mockResolvedValue(false)

    const pb = useMidiPlayback()
    await pb.play()

    expect(guardSpy).toHaveBeenCalledWith(false, 'audio')
    expect(initSpy).not.toHaveBeenCalled()
    expect(pb.isPlaying.value).toBe(false)
  })

  it('proceeds when soundfont downloaded', async () => {
    const store = useModelStore()
    store.models = [{ id: 'soundfont-musyngkite', downloaded: true } as any]
    store.loaded = true
    guardSpy.mockResolvedValue(true)

    const pb = useMidiPlayback()
    await pb.play()

    expect(guardSpy).toHaveBeenCalledWith(true, 'audio')
    expect(initSpy).toHaveBeenCalled()
    expect(pb.isPlaying.value).toBe(true)
  })
})
