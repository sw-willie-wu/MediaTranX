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

  // defineExpose 已於收尾批 W1-3 移除（消費者全受控），此測試改驗內部 5 個狀態存在
  // （vue-test-utils 對 script-setup 頂層綁定可達），非公開契約
  it('internal 5 state refs exist (defineExpose removed in W1-3)', () => {
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

// ── v-model 受控（批 2 Task 2.4 導入；收尾批 W1-3 移除雙軌相容，恆受控）───────────
describe('WhisperAdvancedSettings — v-model 受控', () => {
  const fullValue = {
    word_timestamps: true,
    align: true,
    condition_on_previous_text: false,
    min_silence_duration_ms: 500,
    vad_threshold: 0.5,
  }

  it('無 modelValue prop：內部 ref 用固定預設值', () => {
    const vm = mountIt({ embedded: true }).vm as any
    expect(vm.wordTimestamps).toBe(false)
    expect(vm.align).toBe(false)
    expect(vm.conditionOnPreviousText).toBe(true)
    expect(vm.minSilenceDurationMs).toBe(200)
    expect(vm.vadThreshold).toBe(0.3)
  })

  it('無 modelValue prop：內部 ref 變動仍 emit update:modelValue（不再區分受控/非受控，恆 emit）', async () => {
    const w = mountIt({ embedded: true })
    const vm = w.vm as any
    vm.align = true
    await w.vm.$nextTick()
    expect(vm.align).toBe(true)
    const emitted = w.emitted('update:modelValue')
    expect(emitted).toBeDefined()
    const last = emitted![emitted!.length - 1][0] as Record<string, unknown>
    expect(last.align).toBe(true)
  })

  it('有 modelValue prop：內部 ref 初值來自 modelValue（受控）', () => {
    const vm = mountIt({ embedded: true, modelValue: fullValue }).vm as any
    expect(vm.wordTimestamps).toBe(true)
    expect(vm.align).toBe(true)
    expect(vm.conditionOnPreviousText).toBe(false)
    expect(vm.minSilenceDurationMs).toBe(500)
    expect(vm.vadThreshold).toBe(0.5)
  })

  it('有 modelValue prop：內部使用者操作（改寫曝露的 ref）觸發 update:modelValue 帶完整五欄 patch', async () => {
    const w = mountIt({ embedded: true, modelValue: fullValue })
    const vm = w.vm as any
    vm.vadThreshold = 0.7
    await w.vm.$nextTick()
    const emitted = w.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    const lastPatch = emitted![emitted!.length - 1][0]
    expect(lastPatch).toEqual({ ...fullValue, vad_threshold: 0.7 })
  })

  it('有 modelValue prop：外部改寫 modelValue（父層 setProps）→ 內部 ref 同步更新', async () => {
    const w = mountIt({ embedded: true, modelValue: fullValue })
    await w.setProps({ modelValue: { ...fullValue, min_silence_duration_ms: 1000 } })
    const vm = w.vm as any
    expect(vm.minSilenceDurationMs).toBe(1000)
  })

  it('有 modelValue prop：emit 觸發的 props 回流不會被誤判成外部寫入而重新 emit（無迴圈）', async () => {
    const w = mountIt({ embedded: true, modelValue: fullValue })
    const vm = w.vm as any
    vm.align = false
    await w.vm.$nextTick()
    const emittedCountAfterFirstChange = w.emitted('update:modelValue')!.length
    expect(emittedCountAfterFirstChange).toBe(1)
    // 模擬父層把 emit 出去的值原樣 v-model 傳回（回流）——不應觸發第二次 emit
    const lastPatch = w.emitted('update:modelValue')![0][0]
    await w.setProps({ modelValue: lastPatch })
    await w.vm.$nextTick()
    expect(w.emitted('update:modelValue')!.length).toBe(emittedCountAfterFirstChange)
  })
})
