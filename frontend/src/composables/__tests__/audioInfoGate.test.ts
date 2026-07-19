import { describe, it, expect, vi } from 'vitest'
import { nextTick, ref } from 'vue'
import { isMidiFileName } from '@/composables/useAudioWorkspace'
import { useDomainInfoCache } from '@/composables/useDomainInfoCache'

describe('isMidiFileName', () => {
  it.each(['a.mid', 'B.MIDI', 'x.y.mid'])('%s → true', (n) => {
    expect(isMidiFileName(n)).toBe(true)
  })
  it.each(['a.mp3', 'mid.wav', ''])('%s → false', (n) => {
    expect(isMidiFileName(n)).toBe(false)
  })
})

describe('infoFileId null-gate（MIDI 不打 /audio/info）', () => {
  it('getter 回 null 時 helper 清 info 且不 fetch', async () => {
    const fid = ref<string | null>('f1')
    const name = ref('song.mp3')
    const fetcher = vi.fn().mockResolvedValue({ duration: 1 })
    const infoFileId = () => (isMidiFileName(name.value) ? null : fid.value)
    const cache = useDomainInfoCache<{ duration: number }>({ activeFileId: infoFileId, fetcher })
    await nextTick(); await Promise.resolve()
    expect(fetcher).toHaveBeenCalledTimes(1)
    // 切到 MIDI entry
    fid.value = 'f2'; name.value = 'tune.mid'
    await nextTick()
    expect(cache.info.value).toBeNull()
    expect(fetcher).toHaveBeenCalledTimes(1) // 沒有第二次 fetch
  })
})
