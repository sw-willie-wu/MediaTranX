/**
 * Mount-based render test for ImageCompressPanel
 * Verifies result summary displays correctly for positive/negative/zero saved_ratio.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, nextTick } from 'vue'

function mockT(k: string, params?: Record<string, unknown>): string {
  if (k === 'image.compress.saved' && params?.pct !== undefined) return `Saved ${params.pct}%`
  if (k === 'image.compress.larger' && params?.pct !== undefined) return `${params.pct}% larger`
  if (k === 'image.compress.no_change') return 'No size change'
  if (k === 'image.compress.gif_source_colors' && params?.n !== undefined) return `Source: ${params.n} colors`
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

describe('ImageCompressPanel GIF palette_size', () => {
  it('shows source-colors hint containing palette_size when GIF with palette_size:64 is loaded', () => {
    const w = mountPanel({
      imageInfo: { width: 100, height: 100, format: 'GIF', mode: 'P', file_size: 1000, palette_size: 64 },
    })
    expect(w.text()).toContain('64')
  })

  it('gif_colors defaults to palette_size (64) not 128 when GIF with palette_size:64 is mounted', () => {
    const w = mountPanel({
      imageInfo: { width: 100, height: 100, format: 'GIF', mode: 'P', file_size: 1000, palette_size: 64 },
    })
    const params = (w.vm as { getParams: () => Record<string, unknown> }).getParams()
    expect(params.gif_colors).toBe(64)
  })

  it('gif_colors falls back to 256 when palette_size is absent (no crash)', () => {
    const w = mountPanel({
      imageInfo: { width: 100, height: 100, format: 'GIF', mode: 'P', file_size: 1000 },
    })
    const params = (w.vm as { getParams: () => Record<string, unknown> }).getParams()
    expect(params.gif_colors).toBe(256)
  })

  it('GIF without palette_size does not render source-colors hint', () => {
    const w = mountPanel({
      imageInfo: { width: 100, height: 100, format: 'GIF', mode: 'P', file_size: 1000 },
    })
    expect(w.find('.gif-source-colors-hint').exists()).toBe(false)
  })

  it('gif_colors identity guard: same-image imageInfo reload does not clobber user value; different image does reset', async () => {
    const gifA = { width: 200, height: 100, format: 'GIF', mode: 'P', file_size: 5000, palette_size: 100 }
    const w = mountPanel({ fileId: 'file-a', imageInfo: gifA })
    const vm = w.vm as {
      getParams: () => Record<string, unknown>
      onGifColorsUpdate: (v: number) => void
    }
    // Defaults to palette_size on fresh load
    expect(vm.getParams().gif_colors).toBe(100)
    // Simulate user manually changing gif_colors to 30
    vm.onGifColorsUpdate(30)
    await nextTick()
    expect(vm.getParams().gif_colors).toBe(30)
    // Post-task reload: same fileId, new imageInfo object reference — must NOT clobber
    await w.setProps({ fileId: 'file-a', imageInfo: { ...gifA } })
    expect(vm.getParams().gif_colors).toBe(30)
    // Switch to a different image — must reset to new palette_size
    const gifB = { width: 150, height: 80, format: 'GIF', mode: 'P', file_size: 3000, palette_size: 40 }
    await w.setProps({ fileId: 'file-b', imageInfo: gifB })
    expect(vm.getParams().gif_colors).toBe(40)
  })

  it('source-colors hint is absent for non-GIF images', () => {
    const w = mountPanel({
      imageInfo: { width: 100, height: 100, format: 'PNG', mode: 'RGBA', file_size: 1000 },
    })
    expect(w.find('.gif-source-colors-hint').exists()).toBe(false)
  })
})
