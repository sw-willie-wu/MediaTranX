/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * @vitest-environment jsdom
 *
 * v1.7.1 D — 鎖住 spec 點名的不變量：MIDI active 時公開 activeFileId 仍非 null
 * （編輯/下載依賴它），且不打 /audio/info；非 MIDI 檔則正常載 info。
 */
import { defineComponent } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach, vi } from 'vitest'

const apiFetch = vi.fn(async (path: string) => {
  if (path.startsWith('/audio/info/')) {
    return { ok: true, json: async () => ({ duration: 3, sample_rate: 44100, channels: 2, codec: 'mp3', bitrate: 128, file_size: 100 }) }
  }
  return { ok: true, json: async () => ({}) }
})

vi.mock('@/composables/useApi', async (orig) => {
  const mod = await orig<typeof import('@/composables/useApi')>()
  return { ...mod, apiFetch: (...a: any[]) => apiFetch(...a) }
})
vi.mock('vue-i18n', async (orig) => {
  const mod = await orig<typeof import('vue-i18n')>()
  return { ...mod, useI18n: () => ({ t: (k: string) => k }) }
})
vi.mock('@/composables/usePendingFileListener', () => ({ usePendingFileListener: vi.fn() }))

import { useAudioWorkspace } from '@/composables/useAudioWorkspace'

function mountWorkspace() {
  let ws!: ReturnType<typeof useAudioWorkspace>
  mount(defineComponent({ setup() { ws = useAudioWorkspace(); return () => null } }))
  return ws
}

beforeEach(() => {
  setActivePinia(createPinia())
  apiFetch.mockClear()
})

describe('useAudioWorkspace — MIDI info gate', () => {
  it('選中 MIDI：公開 activeFileId 非 null、不打 /audio/info、audioInfo 為 null', async () => {
    const ws = mountWorkspace()
    ws.addMidiEntry('m1', 'tune.mid')
    await flushPromises()

    expect(ws.activeFileId.value).toBe('m1')          // 編輯/下載路徑不受影響
    expect(ws.audioInfo.value).toBeNull()
    const infoCalls = apiFetch.mock.calls.filter(([p]) => String(p).startsWith('/audio/info/'))
    expect(infoCalls).toHaveLength(0)
  })

  it('選中非 MIDI：打 /audio/info 一次、audioInfo 有值', async () => {
    const ws = mountWorkspace()
    await ws.handleExistingFiles([
      { fileId: 'a1', filename: 'song.mp3', fileSize: 100, mimeType: 'audio/mpeg' },
    ])
    await flushPromises()

    expect(ws.activeFileId.value).toBe('a1')
    const infoCalls = apiFetch.mock.calls.filter(([p]) => String(p).startsWith('/audio/info/'))
    expect(infoCalls).toHaveLength(1)
    expect(ws.audioInfo.value).toMatchObject({ codec: 'mp3' })
  })
})
