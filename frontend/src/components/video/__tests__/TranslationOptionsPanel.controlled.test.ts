/**
 * TranslationOptionsPanel — 受控模式測（統一參數元件案批 2 Task 2.5 v-model 化；收尾批
 * W1-2 移除雙軌相容後，本元件恆受控，檔名沿用舊名不改）。覆蓋：
 *  - 有 modelValue → 初值來自 modelValue、內部狀態變動 emit 完整 patch、外部 modelValue
 *    更新同步回內部狀態（one-shot echo 不重推）。
 *  - context prop 控制 usePersistedModel 的 enabled（pipeline 不寫 localStorage）。
 *  - controlledSeeded：modelValue.translate_model_token 非空時覆蓋 localStorage 初值，
 *    且跳過 onMounted 的 loadPreferences/autoRecommend 自動校正。
 *  - 無 modelValue（mount 時未傳 prop）仍可掛載：onMounted 的 localStorage 還原/自動推薦
 *    邏輯不受 controlledSeeded 保護，行為與過去 uncontrolled 呼叫端一致（見最後一組測試；
 *    純粹是 mount 時序測試，非「不 emit」斷言——emit 一律發生，只是沒有父層在聽）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

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

const modelsState = vi.hoisted(() => ({
  models: [] as Array<{ family: string; variant: string; label: string; size_mb: number; downloaded: boolean; capabilities?: string[] }>,
}))
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    byCapability: (cap: string) => modelsState.models.filter((m) => m.capabilities?.includes(cap)),
    forPanel: (x: unknown[]) => x,
    fetchModels: vi.fn().mockResolvedValue(undefined),
    ensureLoaded: vi.fn(),
  }),
}))

vi.mock('@/stores/settings', () => ({
  useSettingsStore: () => ({
    showAllModels: false,
    deviceInfo: null,
    loadDeviceInfo: vi.fn().mockResolvedValue(undefined),
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

import TranslationOptionsPanel from '../TranslationOptionsPanel.vue'

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    messages: {
      en: {
        video: {
          translate: {
            enable: 'Enable translation', model: 'Translation model', style: 'Translation style',
            keep_names: 'Keep names', keep_names_hint: 'Preserve proper nouns',
            glossary: 'Glossary', glossary_format: 'src=tgt',
          },
        },
        common: {
          target_language: 'Target language',
          translate_style_colloquial: 'Colloquial', translate_style_formal: 'Formal', translate_style_literal: 'Literal',
        },
        settings: { models: { local: 'Local' } },
      },
    },
  })
}

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(TranslationOptionsPanel, { props, global: { plugins: [makeI18n()] } })
}

const defaultValue = {
  enable_translation: false,
  target_language: '',
  translate_model_token: '',
  keep_names: true,
  translate_style: 'colloquial',
  glossary_text: '',
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

describe('TranslationOptionsPanel — 無 modelValue mount（收尾批 W1-2：雙軌相容已移除）', () => {
  it('內部狀態變動仍 emit update:modelValue（不再區分受控/非受控，恆 emit）', async () => {
    const w = mountPanel()
    ;(w.vm as any).enableTranslation = true
    await w.vm.$nextTick()
    const emitted = w.emitted('update:modelValue')!
    expect(emitted).toBeDefined()
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.enable_translation).toBe(true)
  })
})

describe('TranslationOptionsPanel — 受控模式：初值來自 modelValue', () => {
  it('enable_translation/target_language/keep_names/translate_style/glossary_text 皆取自 modelValue', () => {
    const w = mountPanel({
      modelValue: {
        enable_translation: true,
        target_language: 'ja',
        translate_model_token: '',
        keep_names: false,
        translate_style: 'formal',
        glossary_text: 'A → B',
      },
    })
    expect((w.vm as any).enableTranslation).toBe(true)
    expect((w.vm as any).targetLanguage).toBe('ja')
    expect((w.vm as any).keepNames).toBe(false)
    expect((w.vm as any).translateStyle).toBe('formal')
  })

  it('target_language 空字串 → fallback "zh-TW"（同舊 uncontrolled 預設）', () => {
    const w = mountPanel({ modelValue: defaultValue })
    expect((w.vm as any).targetLanguage).toBe('zh-TW')
  })

  it('translate_model_token 非空 → 覆蓋 selectedTranslateModel 初值', () => {
    // 模型清單須含 seeded token 本身，否則既有（非本次改動範圍）的 immediate fallback watch
    // 會在同一個 setup tick 內把它蓋成「第一個已下載模型」——見 TranslationOptionsPanel.vue
    // 檔頭「已知限制」註解。
    modelsState.models = [
      { family: 'gemma4', variant: '4b:Q4_K_M', label: 'Gemma4 4B', size_mb: 3000, downloaded: true, capabilities: ['text'] },
    ]
    const w = mountPanel({ modelValue: { ...defaultValue, translate_model_token: 'gemma4:4b:Q4_K_M' } })
    expect((w.vm as any).selectedTranslateModel).toBe('gemma4:4b:Q4_K_M')
  })
})

describe('TranslationOptionsPanel — 受控模式：內部變動 → emit update:modelValue', () => {
  it('切換 enableTranslation → emit 完整 6 欄 patch', async () => {
    const w = mountPanel({ modelValue: defaultValue })
    ;(w.vm as any).enableTranslation = true
    await w.vm.$nextTick()
    const emitted = w.emitted('update:modelValue')!
    expect(emitted.length).toBeGreaterThan(0)
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.enable_translation).toBe(true)
    expect(last).toHaveProperty('target_language')
    expect(last).toHaveProperty('translate_model_token')
    expect(last).toHaveProperty('keep_names')
    expect(last).toHaveProperty('translate_style')
    expect(last).toHaveProperty('glossary_text')
  })

  it('修改 glossaryText → emit glossary_text 反映新值', async () => {
    const w = mountPanel({ modelValue: { ...defaultValue, enable_translation: true } })
    ;(w.vm as any).glossaryText = 'X → Y'
    await w.vm.$nextTick()
    const emitted = w.emitted('update:modelValue')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.glossary_text).toBe('X → Y')
  })
})

describe('TranslationOptionsPanel — 受控模式：外部 modelValue 更新同步回內部（echo 不重推）', () => {
  it('外部寫入新 modelValue → 內部狀態同步', async () => {
    const w = mountPanel({ modelValue: defaultValue })
    await w.setProps({ modelValue: { ...defaultValue, enable_translation: true, target_language: 'ko', keep_names: false } })
    await w.vm.$nextTick()
    expect((w.vm as any).enableTranslation).toBe(true)
    expect((w.vm as any).targetLanguage).toBe('ko')
    expect((w.vm as any).keepNames).toBe(false)
  })

  it('自身 emit 的值原樣回流（echo）→ 不會二次改寫內部狀態造成迴圈', async () => {
    const w = mountPanel({ modelValue: defaultValue })
    ;(w.vm as any).enableTranslation = true
    await w.vm.$nextTick()
    const emitted = w.emitted('update:modelValue')!
    const echoed = emitted[emitted.length - 1][0]
    // 模擬父層原樣把 emit 出去的值傳回來（SubtitleParams 的 translationValue 是 computed，
    // 若父層邏輯正確通常會是同值）
    await w.setProps({ modelValue: echoed })
    await w.vm.$nextTick()
    expect((w.vm as any).enableTranslation).toBe(true)
  })
})

describe('TranslationOptionsPanel — glossary_text round-trip 不清空使用者輸入（C1 修復）', () => {
  it('打字中、尚未成行（無分隔符,如剛打完 "abc"）→ 父層正規化回流空字串,不清空使用者輸入', async () => {
    const w = mountPanel({ modelValue: { ...defaultValue, enable_translation: true } })
    ;(w.vm as any).glossaryText = 'abc'
    await w.vm.$nextTick()
    // 模擬父層 SubtitleParams：parseGlossaryText('abc') → undefined → glossary: undefined
    // → translationValue computed 的 glossary_text 反算回 ''（glossaryToText(undefined)）
    await w.setProps({ modelValue: { ...defaultValue, enable_translation: true, glossary_text: '' } })
    await w.vm.$nextTick()
    expect((w.vm as any).glossaryText).toBe('abc')
  })

  it('打完一行完整詞條（"abc→xyz"，父層正規化為 "abc → xyz" 帶空格回流）→ 保留使用者原始格式不被改寫', async () => {
    const w = mountPanel({ modelValue: { ...defaultValue, enable_translation: true } })
    ;(w.vm as any).glossaryText = 'abc→xyz'
    await w.vm.$nextTick()
    // 父層 parseGlossaryText('abc→xyz') → {abc:'xyz'} → glossaryToText 反算 'abc → xyz'
    await w.setProps({ modelValue: { ...defaultValue, enable_translation: true, glossary_text: 'abc → xyz' } })
    await w.vm.$nextTick()
    expect((w.vm as any).glossaryText).toBe('abc→xyz')
  })

  it('外部真正改變 glossary（dict 不等價，如切換檔案）→ 正常覆蓋成父層新值', async () => {
    const w = mountPanel({ modelValue: { ...defaultValue, enable_translation: true, glossary_text: '' } })
    expect((w.vm as any).glossaryText).toBe('')
    await w.setProps({ modelValue: { ...defaultValue, enable_translation: true, glossary_text: 'X → Y' } })
    await w.vm.$nextTick()
    expect((w.vm as any).glossaryText).toBe('X → Y')
  })
})

describe('TranslationOptionsPanel — context prop 控制 usePersistedModel enabled', () => {
  it('context 未傳（預設 tool）→ 選擇模型寫入 localStorage（既有行為不變）', async () => {
    const w = mountPanel({ storageKey: 'subtitle_translate_model' })
    ;(w.vm as any).selectedTranslateModel = 'gemma4:4b:Q4_K_M'
    await w.vm.$nextTick()
    expect(localStorage.getItem('subtitle_translate_model')).toBe('gemma4:4b:Q4_K_M')
  })

  it('context="pipeline" → 選擇模型不寫入 localStorage', async () => {
    const w = mountPanel({ storageKey: 'subtitle_translate_model', context: 'pipeline' })
    ;(w.vm as any).selectedTranslateModel = 'gemma4:4b:Q4_K_M'
    await w.vm.$nextTick()
    expect(localStorage.getItem('subtitle_translate_model')).toBeNull()
  })
})

describe('TranslationOptionsPanel — controlledSeeded：跳過 onMounted 自動校正', () => {
  // 兩個模型都在清單中（皆 downloaded）——seeded token 本身有效存在於 options，
  // 才不會被「先於 onMounted 執行」的既有 immediate fallback watch（非本次雙軌化範圍,
  // 沿舊邏輯不動）意外覆寫，測試才能單純驗證 controlledSeeded 對 onMounted 段的保護
  // （見 TranslationOptionsPanel.vue 檔頭「已知限制」註解／task report concerns）。
  beforeEach(() => {
    modelsState.models = [
      { family: 'gemma4', variant: '4b:Q4_K_M', label: 'Gemma4 4B', size_mb: 3000, downloaded: true, capabilities: ['text'] },
      { family: 'stale', variant: '1b:Q8_0', label: 'Stale 1B', size_mb: 1000, downloaded: true, capabilities: ['text'] },
    ]
  })

  it('modelValue.translate_model_token 非空 → mount 後（onMounted resolve）不被 localStorage 殘留值覆蓋', async () => {
    localStorage.setItem('translate-preferences-subtitle_translate_model', JSON.stringify({ translateModel: 'stale:1b:Q8_0' }))
    const w = mountPanel({
      storageKey: 'subtitle_translate_model',
      modelValue: { ...defaultValue, translate_model_token: 'gemma4:4b:Q4_K_M' },
    })
    await flushPromises()
    expect((w.vm as any).selectedTranslateModel).toBe('gemma4:4b:Q4_K_M')
  })

  it('無 modelValue（uncontrolled）→ onMounted 仍會用 localStorage 殘留值還原（既有行為不變）', async () => {
    localStorage.setItem('translate-preferences-subtitle_translate_model', JSON.stringify({ translateModel: 'stale:1b:Q8_0' }))
    const w = mountPanel({ storageKey: 'subtitle_translate_model' })
    await flushPromises()
    expect((w.vm as any).selectedTranslateModel).toBe('stale:1b:Q8_0')
  })
})
