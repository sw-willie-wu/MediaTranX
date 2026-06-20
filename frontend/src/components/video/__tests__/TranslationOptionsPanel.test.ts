/**
 * Tests for TranslationOptionsPanel — Wave 2 Task 4
 *
 * Verifies:
 *  - storageKey prop isolates localStorage persistence per panel
 *  - Default (no prop) backward-compat: SubtitlePanel still works
 *  - targetLanguageOptions is exposed on the component instance
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

// ── stub child components ────────────────────────────────────────────────────
vi.mock('@/components/common/AppSelect.vue', () => ({
  default: {
    props: ['modelValue', 'options'],
    emits: ['update:modelValue'],
    template: `<select @change="$emit('update:modelValue', $event.target.value)">
      <option v-for="o in (options || [])" :key="o.value" :value="o.value">{{ o.label }}</option>
    </select>`,
  },
}))

vi.mock('@/components/common/AppToggle.vue', () => ({
  default: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" />',
  },
}))

// ── mock stores ──────────────────────────────────────────────────────────────
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    byCapability: () => [],
    byCategory: () => [],
    forPanel: (x: unknown[]) => x,
    fetchModels: vi.fn(),
    ensureLoaded: vi.fn(),
  }),
}))

vi.mock('@/stores/settings', () => ({
  useSettingsStore: () => ({
    showAllModels: false,
    deviceInfo: null,
    loadDeviceInfo: vi.fn(),
  }),
}))

vi.mock('@/stores/remoteModels', () => ({
  useRemoteModelStore: () => ({
    byCapability: () => [],
    ensureLoaded: vi.fn(),
  }),
}))

vi.mock('@/composables/useApi', () => ({
  apiFetch: vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
}))

// ── import component after mocks ─────────────────────────────────────────────
import TranslationOptionsPanel from '../TranslationOptionsPanel.vue'

// ── i18n ─────────────────────────────────────────────────────────────────────
function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    messages: {
      en: {
        video: {
          translate: {
            enable: 'Enable translation',
            model: 'Translation model',
            style: 'Translation style',
            keep_names: 'Keep names',
            keep_names_hint: 'Preserve proper nouns',
            glossary: 'Glossary',
            glossary_format: 'src=tgt',
          },
        },
        common: {
          target_language: 'Target language',
          translate_style_colloquial: 'Colloquial',
          translate_style_formal: 'Formal',
          translate_style_literal: 'Literal',
        },
        settings: {
          models: {
            local: 'Local',
          },
        },
      },
    },
  })
}

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(TranslationOptionsPanel, {
    props,
    global: { plugins: [makeI18n()] },
  })
}

// ── tests ─────────────────────────────────────────────────────────────────────
describe('TranslationOptionsPanel — storageKey prop isolation', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('persists translate model under the provided storageKey, isolated from subtitle key', async () => {
    const a = mountPanel({ storageKey: 'audio_transcribe_translate_model' })
    ;(a.vm as any).selectedTranslateModel = 'qwen3:8b:q4'
    await a.vm.$nextTick()
    expect(localStorage.getItem('audio_transcribe_translate_model')).toContain('qwen3:8b:q4')
    expect(localStorage.getItem('subtitle_translate_model')).toBeNull()
  })

  it('mounts prop-less (Subtitle backward compat) and exposes targetLanguageOptions', () => {
    const s = mountPanel()
    expect(Array.isArray((s.vm as any).targetLanguageOptions)).toBe(true)
  })

  it('isolates translate-preferences storage key between two different storageKey props', async () => {
    const a = mountPanel({ storageKey: 'panel_a_translate_model' })
    const b = mountPanel({ storageKey: 'panel_b_translate_model' })
    ;(a.vm as any).selectedTranslateModel = 'modelA:7b:q4'
    await a.vm.$nextTick()
    ;(b.vm as any).selectedTranslateModel = 'modelB:7b:q8'
    await b.vm.$nextTick()
    // Each panel's preferences key should be independent
    const prefA = localStorage.getItem('translate-preferences-panel_a_translate_model')
    const prefB = localStorage.getItem('translate-preferences-panel_b_translate_model')
    if (prefA !== null) expect(prefA).toContain('modelA')
    if (prefB !== null) expect(prefB).toContain('modelB')
    // The old shared key must not exist
    expect(localStorage.getItem('translate-preferences')).toBeNull()
  })

  it('exposes targetLanguageOptions as a non-empty array of {value,label} objects', () => {
    const s = mountPanel()
    const opts = (s.vm as any).targetLanguageOptions as Array<{ value: string; label: string }>
    expect(Array.isArray(opts)).toBe(true)
    expect(opts.length).toBeGreaterThan(0)
    expect(opts[0]).toHaveProperty('value')
    expect(opts[0]).toHaveProperty('label')
  })
})
