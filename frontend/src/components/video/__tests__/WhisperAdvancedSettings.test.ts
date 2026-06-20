/**
 * Tests for WhisperAdvancedSettings — Wave 2.1 Task 1
 *
 * Verifies:
 *  - embedded=true: renders section_title label + all 5 fields directly (no self-toggle)
 *  - embedded=false (default): self-collapsing toggle, fields hidden until expanded
 *  - All 5 refs are exposed on the component instance
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

// ── stub child components ────────────────────────────────────────────────────
vi.mock('@/components/common/AppToggle.vue', () => ({
  default: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template:
      '<label><input type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" /><slot /></label>',
  },
}))

vi.mock('@/components/common/AppRange.vue', () => ({
  default: {
    props: ['modelValue', 'min', 'max', 'step'],
    emits: ['update:modelValue'],
    template: '<input type="range" :value="modelValue" @input="$emit(\'update:modelValue\', +$event.target.value)" />',
  },
}))

// ── import component after mocks ─────────────────────────────────────────────
import WhisperAdvancedSettings from '../WhisperAdvancedSettings.vue'

// ── i18n ─────────────────────────────────────────────────────────────────────
function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    messages: {
      en: {
        video: {
          whisper_advanced: {
            title: 'Advanced Segmentation',
            title_hint: '(for multi-speaker)',
            section_title: 'Segmentation Settings',
            independent_segments: 'Independent segment recognition',
            independent_hint: 'Disable context association to prevent sentence merging',
            word_timestamps: 'Word-level timestamps',
            word_timestamps_hint: 'More precise segmentation boundaries',
            align: 'Forced Alignment',
            align_hint: 'Use Wav2Vec2 to refine word timestamps for more accurate subtitles',
            min_silence: 'Min. silence duration',
            milliseconds: 'ms',
            min_silence_hint: 'Pauses exceeding this duration will create a new segment (default 200ms)',
            vad_threshold: 'VAD Sensitivity',
            vad_threshold_hint: 'Lower values are more sensitive, more likely to segment (default 0.3)',
          },
        },
      },
    },
  })
}

function mountIt(props: Record<string, unknown> = {}) {
  return mount(WhisperAdvancedSettings, {
    props,
    global: { plugins: [makeI18n()] },
  })
}

// ── tests ─────────────────────────────────────────────────────────────────────
describe('WhisperAdvancedSettings', () => {
  it('embedded=true: renders section heading + fields directly, no self-toggle', () => {
    const w = mountIt({ embedded: true })
    // section_title label is shown
    expect(w.text()).toContain('Segmentation Settings')
    // the self-collapsing toggle title is NOT shown
    expect(w.text()).not.toContain('Advanced Segmentation')
    // a real field is visible without any user interaction
    expect(w.text()).toContain('VAD Sensitivity')
  })

  it('embedded=false (default): self-collapsing toggle, fields hidden until expanded', () => {
    const w = mountIt()
    // toggle label is visible
    expect(w.text()).toContain('Advanced Segmentation')
    // fields are hidden while collapsed
    expect(w.text()).not.toContain('VAD Sensitivity')
  })

  it('exposes the 5 refs', () => {
    const vm = mountIt({ embedded: true }).vm as any
    for (const k of [
      'wordTimestamps',
      'align',
      'conditionOnPreviousText',
      'minSilenceDurationMs',
      'vadThreshold',
    ]) {
      expect(vm[k]).not.toBeUndefined()
    }
  })
})
