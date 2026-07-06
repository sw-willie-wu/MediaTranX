/**
 * Mount-based render test for VideoTranscodePanel
 * Verifies that GIF/APNG output produces correct getParams() payload.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, nextTick } from 'vue'

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

import VideoTranscodePanel from '@/components/video/panels/VideoTranscodePanel.vue'

const STUBS = ['AppRange', 'AppSelect', 'SettingsCollapsible']

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(VideoTranscodePanel, {
    props: {
      fileId: null,
      currentFileName: 'test.mp4',
      ...props,
    },
    global: {
      mocks: {
        $t: (k: string) => k,
      },
      stubs: STUBS,
    },
  })
}

describe('VideoTranscodePanel getParams() for GIF/APNG', () => {
  it('gif params carry fps and omit codec/crf', async () => {
    const w = mountPanel()
    ;(w.vm as any).outputFormat = 'gif'
    await nextTick()
    const params = (w.vm as any).getParams()
    expect(params).toMatchObject({ output_format: 'gif', fps: 12 })
    expect(params).not.toHaveProperty('video_codec')
    expect(params).not.toHaveProperty('crf')
    expect(params).not.toHaveProperty('audio_codec')
  })
})
