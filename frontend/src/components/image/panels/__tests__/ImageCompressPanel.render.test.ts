/**
 * Mount-based render test for ImageCompressPanel
 * Verifies result summary displays correctly for positive/negative/zero saved_ratio.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

function mockT(k: string, params?: Record<string, unknown>): string {
  if (k === 'image.compress.saved' && params?.pct !== undefined) return `Saved ${params.pct}%`
  if (k === 'image.compress.larger' && params?.pct !== undefined) return `${params.pct}% larger`
  if (k === 'image.compress.no_change') return 'No size change'
  return k
}

// Must be hoisted before the SFC import
vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: mockT,
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
        $t: mockT,
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

  it('renders "larger" wording (non-green) when saved_ratio is negative', () => {
    const w = mountPanel({
      resultMeta: { saved_ratio: -0.30, output_size: 13000, original_size: 10000 },
    })
    // Should show the abs percentage
    expect(w.text()).toContain('30%')
    // Should contain "larger" wording
    expect(w.text()).toContain('larger')
    // Must NOT say "Saved"
    expect(w.text()).not.toContain('Saved')
    // Must NOT apply success-green class
    const summary = w.find('.compress-result-summary')
    expect(summary.classes()).not.toContain('compress-result-saved')
  })

  it('renders "No size change" wording (non-green) when saved_ratio is 0', () => {
    const w = mountPanel({
      resultMeta: { saved_ratio: 0, output_size: 10000, original_size: 10000 },
    })
    expect(w.text()).toContain('No size change')
    // Must NOT say "Saved"
    expect(w.text()).not.toContain('Saved')
    // Must NOT apply success-green class
    const summary = w.find('.compress-result-summary')
    expect(summary.classes()).not.toContain('compress-result-saved')
  })
})
