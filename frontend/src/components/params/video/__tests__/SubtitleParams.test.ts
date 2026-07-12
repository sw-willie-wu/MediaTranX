/**
 * SubtitleParams.vue 單測（統一參數元件案批 2 Task 2.5——例外殼工具表單本體）。
 * 覆蓋：欄位佈局（source_language/model_size/output_format 頂層＋SettingsCollapsible 進階區含
 * vocal_separation/WhisperAdvancedSettings）、source_language 有無 languageOptions 兩種呈現、
 * whisper picker persisted seed（沿 SummaryParams pattern）、翻譯 gate 開關（seed 'zh-TW'／
 * 清空七欄+keep_names/translate_style/glossary）、glossary text↔dict round trip。
 * （收尾批 W1-4：composite 註冊死碼已刪，本檔不再覆蓋 composite——SubtitlePanel 殼有自己的
 * agentSchema，composite 過去始終無消費者。）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

const modelsState = vi.hoisted(() => ({
  models: [] as Array<{
    family: string
    variant: string
    label: string
    size_mb: number
    downloaded: boolean
    capabilities?: string[]
    category?: string
  }>,
}))
const ensureLoadedMock = vi.hoisted(() => vi.fn())
const fetchModelsMock = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    byCapability: (cap: string) => modelsState.models.filter((m) => m.capabilities?.includes(cap)),
    byCategory: (cat: string) => modelsState.models.filter((m) => m.category === cat),
    forPanel: (items: unknown[]) => items,
    ensureLoaded: ensureLoadedMock,
    fetchModels: fetchModelsMock,
    models: modelsState.models,
  }),
}))

const remoteEnsureLoadedMock = vi.hoisted(() => vi.fn())
vi.mock('@/stores/remoteModels', () => ({
  useRemoteModelStore: () => ({
    byCapability: () => [] as unknown[],
    ensureLoaded: remoteEnsureLoadedMock,
  }),
}))

vi.mock('@/stores/settings', () => ({
  useSettingsStore: () => ({
    showAllModels: false,
    deviceInfo: null,
    loadDeviceInfo: vi.fn().mockResolvedValue(undefined),
  }),
}))

vi.mock('@/composables/useApi', () => ({
  apiFetch: vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
}))

import SubtitleParams from '../SubtitleParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import WhisperAdvancedSettings from '@/components/video/WhisperAdvancedSettings.vue'
import TranslationOptionsPanel from '@/components/video/TranslationOptionsPanel.vue'

function mountParams(
  params: Record<string, unknown>,
  context: 'tool' | 'pipeline' = 'tool',
  languageOptions?: Array<{ value: string; label: string }>,
) {
  return mount(SubtitleParams, {
    props: { params, context, fileInfo: null, languageOptions },
    global: {
      mocks: { $t: (k: string) => k },
    },
  })
}

function selects(w: ReturnType<typeof mountParams>) {
  return w.findAllComponents(AppSelect)
}

beforeEach(() => {
  modelsState.models = []
  localStorage.clear()
  ensureLoadedMock.mockClear()
  remoteEnsureLoadedMock.mockClear()
  fetchModelsMock.mockClear()
})

describe('SubtitleParams — 掛載時載入模型清單', () => {
  it('mount 後 modelStore.ensureLoaded 被呼叫', () => {
    mountParams({})
    expect(ensureLoadedMock).toHaveBeenCalled()
  })
})

describe('SubtitleParams — 佈局（沿舊 SubtitlePanel：source_language/model_size/output_format 頂層，vocal_separation/WhisperAdvanced 進階區）', () => {
  it('languageOptions 有值時：三個頂層 AppSelect（source_language/model_size/output_format）', () => {
    const w = mountParams({}, 'tool', [{ value: 'en', label: 'English' }])
    // selects 也含 TranslationOptionsPanel 內部（gate 關閉時不渲染），故只斷言 >= 3
    expect(selects(w).length).toBeGreaterThanOrEqual(3)
  })

  it('有 SettingsCollapsible 進階區', () => {
    const w = mountParams({})
    expect(w.findComponent(SettingsCollapsible).exists()).toBe(true)
  })

  it('WhisperAdvancedSettings 以 embedded=true 掛載', () => {
    const w = mountParams({})
    const whisperAdv = w.findComponent(WhisperAdvancedSettings)
    expect(whisperAdv.exists()).toBe(true)
    expect(whisperAdv.props('embedded')).toBe(true)
  })

  it('TranslationOptionsPanel 內嵌，受控（有 modelValue prop）', () => {
    const w = mountParams({})
    const panel = w.findComponent(TranslationOptionsPanel)
    expect(panel.exists()).toBe(true)
    expect(panel.props('modelValue')).toBeDefined()
  })
})

describe('SubtitleParams — source_language：有/無 languageOptions 兩種呈現', () => {
  it('languageOptions 未傳/空 → 退純文字輸入（非 AppSelect）', () => {
    const w = mountParams({ source_language: 'en' })
    const input = w.find('input[type="text"]')
    expect(input.exists()).toBe(true)
    expect((input.element as HTMLInputElement).value).toBe('en')
  })

  it('純文字輸入 @change → commitPatch source_language', async () => {
    const w = mountParams({})
    const input = w.find('input[type="text"]')
    await input.setValue('ja')
    await input.trigger('change')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.source_language).toBe('ja')
  })

  it('languageOptions 有值 → 呈現 AppSelect，modelValue=params.source_language', () => {
    const w = mountParams({ source_language: 'en' }, 'tool', [
      { value: '', label: 'auto' },
      { value: 'en', label: 'English' },
    ])
    const select = selects(w)[0]
    expect(select.props('modelValue')).toBe('en')
    expect(select.props('options')).toEqual([
      { value: '', label: 'auto' },
      { value: 'en', label: 'English' },
    ])
  })
})

describe('SubtitleParams — whisper picker（欄位名 model_size，非 whisper_model_size）', () => {
  it('modelValue = params.model_size', () => {
    const w = mountParams({ model_size: 'large-v3' }, 'tool', [{ value: 'en', label: 'English' }])
    const select = selects(w)[1] // [0]=source_language, [1]=whisper
    expect(select.props('modelValue')).toBe('large-v3')
  })

  it('選擇 → emit update:params 含 model_size', async () => {
    const w = mountParams({ model_size: 'medium' }, 'tool', [{ value: 'en', label: 'English' }])
    const select = selects(w)[1]
    await select.vm.$emit('update:modelValue', 'small')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.model_size).toBe('small')
  })

  it('tool context：localStorage 有值且 params===defaults → 掛載時 seed patch', () => {
    localStorage.setItem('subtitle_whisper_model', 'large-v3')
    const w = mountParams({ model_size: 'medium' })
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.model_size).toBe('large-v3')
  })

  it('pipeline context：不讀 localStorage', () => {
    localStorage.setItem('subtitle_whisper_model', 'large-v3')
    const w = mountParams({ model_size: 'medium' }, 'pipeline')
    expect(w.emitted('update:params')).toBeUndefined()
  })

  it('fallback：清單載入含已下載項且目前 token 未對應任何選項 → 自動選中（tool context）', async () => {
    modelsState.models = [
      { family: 'whisper', variant: 'small', label: 'Small', size_mb: 500, downloaded: true, category: 'stt' },
    ]
    const w = mountParams({ model_size: 'medium' })
    await flushPromises()
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.model_size).toBe('small')
  })
})

describe('SubtitleParams — output_format', () => {
  it('modelValue = params.output_format（default "srt"）', () => {
    const w = mountParams({}, 'tool', [{ value: 'en', label: 'English' }])
    const select = selects(w)[2]
    expect(select.props('modelValue')).toBe('srt')
  })

  it('切換 → emit update:params 含 output_format', async () => {
    const w = mountParams({}, 'tool', [{ value: 'en', label: 'English' }])
    const select = selects(w)[2]
    await select.vm.$emit('update:modelValue', 'vtt')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.output_format).toBe('vtt')
  })
})

describe('SubtitleParams — vocal_separation', () => {
  it('切換 → commitPatch vocal_separation', async () => {
    const w = mountParams({ vocal_separation: false })
    // AppToggle[0] 是 TranslationOptionsPanel 內嵌的「啟用翻譯」開關（恆渲染，與翻譯 gate 無關）；
    // vocal_separation 開關是 SubtitleParams 自己在 SettingsCollapsible 裡的第二個 AppToggle。
    const toggle = w.findAllComponents(AppToggle)[1]
    await toggle.vm.$emit('update:modelValue', true)
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.vocal_separation).toBe(true)
  })
})

describe('SubtitleParams — WhisperAdvancedSettings v-model 寫回五個 params 欄位', () => {
  it('update:modelValue → emit update:params 含五欄正確值', async () => {
    const w = mountParams({})
    const whisperAdv = w.findComponent(WhisperAdvancedSettings)
    await whisperAdv.vm.$emit('update:modelValue', {
      word_timestamps: true,
      align: true,
      condition_on_previous_text: false,
      min_silence_duration_ms: 1000,
      vad_threshold: 0.7,
    })
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.word_timestamps).toBe(true)
    expect(last.align).toBe(true)
    expect(last.min_silence_duration_ms).toBe(1000)
    expect(last.vad_threshold).toBe(0.7)
  })
})

describe('SubtitleParams — 翻譯 gate（target_language 非空字串代表已啟用）', () => {
  it('未啟用時：TranslationOptionsPanel modelValue.enable_translation=false, target_language=""', () => {
    const w = mountParams({})
    const panel = w.findComponent(TranslationOptionsPanel)
    const mv = panel.props('modelValue') as Record<string, unknown>
    expect(mv.enable_translation).toBe(false)
    expect(mv.target_language).toBe('')
  })

  it('gate 開啟（enable_translation:true, target_language 空）→ seed target_language "zh-TW"', async () => {
    const w = mountParams({})
    const panel = w.findComponent(TranslationOptionsPanel)
    await panel.vm.$emit('update:modelValue', {
      enable_translation: true,
      target_language: '',
      translate_model_token: '',
      keep_names: true,
      translate_style: 'colloquial',
      glossary_text: '',
    })
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.target_language).toBe('zh-TW')
    expect(last.keep_names).toBe(true)
    expect(last.translate_style).toBe('colloquial')
  })

  it('gate 開啟且已選本地翻譯模型 token → 展開 translate_model_family/size', async () => {
    const w = mountParams({})
    const panel = w.findComponent(TranslationOptionsPanel)
    await panel.vm.$emit('update:modelValue', {
      enable_translation: true,
      target_language: 'ja',
      translate_model_token: 'gemma4:4b:Q4_K_M',
      keep_names: false,
      translate_style: 'formal',
      glossary_text: '',
    })
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.target_language).toBe('ja')
    expect(last.translate_model_family).toBe('gemma4')
    expect(last.translate_model_size).toBe('4b')
    expect(last.translate_quantization).toBe('Q4_K_M')
    expect(last.keep_names).toBe(false)
    expect(last.translate_style).toBe('formal')
  })

  it('gate 關閉 → 清空 target_language/keep_names/translate_style/glossary/translate_* 七欄', async () => {
    const w = mountParams({
      target_language: 'ja',
      translate_model_family: 'gemma4',
      translate_model_size: '4b',
      keep_names: false,
      translate_style: 'formal',
      glossary: { A: 'B' },
    })
    const panel = w.findComponent(TranslationOptionsPanel)
    await panel.vm.$emit('update:modelValue', {
      enable_translation: false,
      target_language: 'ja',
      translate_model_token: 'gemma4:4b:',
      keep_names: false,
      translate_style: 'formal',
      glossary_text: 'A → B',
    })
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.target_language).toBeUndefined()
    expect(last.keep_names).toBeUndefined()
    expect(last.translate_style).toBeUndefined()
    expect(last.glossary).toBeUndefined()
    expect(last.translate_model_family).toBeUndefined()
    expect(last.translate_model_size).toBeUndefined()
    expect(last.translate_remote).toBeUndefined()
  })
})

describe('SubtitleParams — glossary text ↔ dict round trip', () => {
  it('params.glossary 為 dict → TranslationOptionsPanel modelValue.glossary_text 轉字串', () => {
    const w = mountParams({ target_language: 'en', glossary: { Claude: 'Claude', 台北: 'Taipei' } })
    const panel = w.findComponent(TranslationOptionsPanel)
    const mv = panel.props('modelValue') as Record<string, unknown>
    expect(mv.glossary_text).toBe('Claude → Claude\n台北 → Taipei')
  })

  it('TranslationOptionsPanel emit glossary_text → 解析回 dict 寫入 params.glossary', async () => {
    const w = mountParams({ target_language: 'en' })
    const panel = w.findComponent(TranslationOptionsPanel)
    await panel.vm.$emit('update:modelValue', {
      enable_translation: true,
      target_language: 'en',
      translate_model_token: '',
      keep_names: true,
      translate_style: 'colloquial',
      glossary_text: 'Claude = Claude',
    })
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.glossary).toEqual({ Claude: 'Claude' })
  })

  it('glossary_text 空白 → glossary undefined（不進 params）', async () => {
    const w = mountParams({ target_language: 'en' })
    const panel = w.findComponent(TranslationOptionsPanel)
    await panel.vm.$emit('update:modelValue', {
      enable_translation: true,
      target_language: 'en',
      translate_model_token: '',
      keep_names: true,
      translate_style: 'colloquial',
      glossary_text: '   ',
    })
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.glossary).toBeUndefined()
  })
})
