/**
 * Mount-based render test for ImageCompressPanel
 * Verifies "Saved X%" result summary displays when resultMeta is provided.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

// Must be hoisted before the SFC import
vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (k: string, params?: Record<string, unknown>) => {
      if (params?.pct !== undefined) return `Saved ${params.pct}%`
      return k
    },
  }),
}))

vi.mock('@/composables/useSubmitTask', () => ({
  useSubmitTask: () => ({ submitTask: vi.fn(), isProcessing: ref(false) }),
}))

vi.mock('@/composables/useAgentPanelHost', () => ({
  useAgentPanelHost: vi.fn(),
}))

import ImageCompressPanel from '@/components/image/panels/ImageCompressPanel.vue'

const STUBS = ['AppRange', 'AppSelect', 'AppToggle', 'SettingsCollapsible']

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(ImageCompressPanel, {
    props: {
      fileId: null,
      currentFileName: 'test.jpg',
      imageInfo: null,
      ...props,
    },
    global: {
      mocks: {
        $t: (k: string, params?: Record<string, unknown>) => {
          if (params?.pct !== undefined) return `Saved ${params.pct}%`
          return k
        },
      },
      stubs: STUBS,
    },
  })
}

describe('ImageCompressPanel resultMeta display', () => {
  it('renders "42%" when resultMeta.saved_ratio is 0.42', () => {
    const w = mountPanel({
      resultMeta: { saved_ratio: 0.42, output_size: 5800, original_size: 10000 },
    })
    expect(w.text()).toContain('42%')
  })

  it('renders before→after sizes alongside the percentage', () => {
    const w = mountPanel({
      resultMeta: { saved_ratio: 0.42, output_size: 5800, original_size: 10000 },
    })
    // Both sizes should appear as human-readable strings
    expect(w.text()).toMatch(/KB/)
  })

  it('renders nothing extra when resultMeta is null', () => {
    const w = mountPanel({ resultMeta: null })
    expect(w.find('.compress-result-summary').exists()).toBe(false)
  })

  it('renders nothing extra when resultMeta has no saved_ratio', () => {
    const w = mountPanel({ resultMeta: { some_other_field: 'x' } })
    expect(w.find('.compress-result-summary').exists()).toBe(false)
  })
})
