/**
 * Mount-based test for VideoInterpolatePanel getParams()/preflight()
 * (multi-select batch submit exposes shared params without file_id).
 *
 * 注意:transcode 面板無 store,此面板用 useModelStore/useModelGuard/usePersistedModel,
 * 直接沿用 transcode 掛載會炸 "no active Pinia" — 這裡以 vi.mock 模組取代。
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

// Must be hoisted before the SFC import
vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (k: string) => k,
  }),
}))

vi.mock('@/composables/useSubmitTask', () => ({
  useSubmitTask: () => ({ submitTask: vi.fn(), isProcessing: ref(false) }),
}))

vi.mock('@/composables/useAgentPanelHost', () => ({
  useAgentPanelHost: vi.fn(),
}))

vi.mock('@/composables/useModelGuard', () => ({
  useModelGuard: () => ({ guardModelReady: vi.fn(async () => true) }),
}))

vi.mock('@/composables/usePersistedModel', () => ({
  usePersistedModel: (_key: string, fallback: string) => ref(fallback),
}))

vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    ensureLoaded: vi.fn(),
    byCategory: vi.fn(() => []),
    forPanel: vi.fn(() => [{ variant: 'v4.26', label: 'RIFE v4.26', downloaded: true }]),
  }),
}))

import VideoInterpolatePanel from '@/components/video/panels/VideoInterpolatePanel.vue'

const STUBS = ['AppRange', 'AppSelect', 'SettingsCollapsible']

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(VideoInterpolatePanel, {
    props: {
      fileId: 'f1',
      currentFileName: 'test.mp4',
      mediaInfo: { fps: 30 },
      ...props,
    },
    global: {
      mocks: { $t: (k: string) => k },
      stubs: STUBS,
    },
  })
}

describe('VideoInterpolatePanel getParams()', () => {
  it('returns shared params without file_id', () => {
    const w = mountPanel()
    const params = (w.vm as any).getParams()
    expect(params.file_id).toBeUndefined()
    expect(params.model).toBe('v4.26')
    expect(params.mode).toBe('2x')
    expect(params.output_format).toBe('mp4')
    expect(params.video_codec).toBe('h264')
  })

  it('preflight passes when model ready and fps sane', async () => {
    const w = mountPanel()
    await expect((w.vm as any).preflight()).resolves.toBe(true)
  })
})
