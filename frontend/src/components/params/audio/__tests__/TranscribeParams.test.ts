/**
 * TranscribeParams.vue 單測（統一參數元件 spec §5；批 3 Task 3.4——批 3 最大工具）。
 * 覆蓋：欄位佈局（model/source_language/output_format 頂層＋SettingsCollapsible 進階區）、
 * source_language 元件內載入（tool context 才發 GET，pipeline 退純文字輸入）、whisper picker
 * persisted seed、翻譯 gate（獨立 translate bool，非 target_language 判準）、summarize
 * toggle+picker（第三 composite）、glossary round trip、三 composite 註冊（covers 不重疊）。
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
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    byCapability: (cap: string) => modelsState.models.filter((m) => m.capabilities?.includes(cap)),
    byCategory: (cat: string) => modelsState.models.filter((m) => m.category === cat),
    forPanel: (items: unknown[]) => items,
    ensureLoaded: ensureLoadedMock,
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

const apiFetchMock = vi.hoisted(() => vi.fn().mockResolvedValue({ ok: true, json: async () => [] }))
vi.mock('@/composables/useApi', () => ({
  apiFetch: apiFetchMock,
}))

import TranscribeParams from '../TranscribeParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import WhisperAdvancedSettings from '@/components/video/WhisperAdvancedSettings.vue'
import TranslationOptionsPanel from '@/components/video/TranslationOptionsPanel.vue'
import type { AgentCompositeField } from '../../types'

function mountParams(
  params: Record<string, unknown>,
  context: 'tool' | 'pipeline' = 'tool',
  registerComposite?: (c: AgentCompositeField) => () => void,
) {
  return mount(TranscribeParams, {
    props: { params, context, fileInfo: null },
    global: {
      mocks: { $t: (k: string) => k },
      provide: registerComposite ? { registerComposite } : {},
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
  apiFetchMock.mockClear()
  apiFetchMock.mockResolvedValue({ ok: true, json: async () => [] })
})

describe('TranscribeParams — 掛載時載入模型清單', () => {
  it('mount 後 modelStore/remoteStore.ensureLoaded 被呼叫', () => {
    mountParams({})
    expect(ensureLoadedMock).toHaveBeenCalled()
    expect(remoteEnsureLoadedMock).toHaveBeenCalled()
  })
})

describe('TranscribeParams — source_language 元件內載入（僅 tool context 發 GET）', () => {
  it('context=tool → onMounted 呼叫 GET /audio/transcribe/languages', () => {
    mountParams({}, 'tool')
    expect(apiFetchMock).toHaveBeenCalledWith('/audio/transcribe/languages')
  })

  it('context=pipeline → 不發 GET /audio/transcribe/languages，退純文字輸入', async () => {
    // 注意：TranslationOptionsPanel 自己在 onMounted 無條件呼叫 apiFetch('/llm/translate/styles')
    // （與 context 無關，非本檔遷移範圍——見該元件檔頭註解），故僅斷言「本元件的」語言清單
    // GET 未被呼叫，不斷言 apiFetch 全域零呼叫次數。
    const w = mountParams({ source_language: 'en' }, 'pipeline')
    await flushPromises()
    expect(apiFetchMock).not.toHaveBeenCalledWith('/audio/transcribe/languages')
    const input = w.find('input[type="text"]')
    expect(input.exists()).toBe(true)
    expect((input.element as HTMLInputElement).value).toBe('en')
  })

  it('languages 載入成功 → source_language 呈現 AppSelect', async () => {
    // TranslationOptionsPanel 子元件的 onMounted（loadTranslateStyles 呼 /llm/translate/styles）
    // 比父層 TranscribeParams 的 onMounted 先觸發（Vue 子先於父掛載）——用 mockImplementation
    // 依 URL 分流，避免 mockResolvedValueOnce 排隊到錯的呼叫。
    apiFetchMock.mockImplementation(async (url: string) => {
      if (url === '/audio/transcribe/languages') {
        return { ok: true, json: async () => [{ value: '', label: '' }, { value: 'en', label: 'English' }] }
      }
      return { ok: true, json: async () => [] }
    })
    const w = mountParams({ source_language: 'en' }, 'tool')
    await flushPromises()
    const select = selects(w)[1] // [0]=whisper, [1]=source_language
    expect(select.props('modelValue')).toBe('en')
  })
})

describe('TranscribeParams — 佈局（model/source_language/output_format 頂層，vocal_separation/WhisperAdvanced 進階區）', () => {
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

describe('TranscribeParams — whisper picker（欄位名 model_size；persist key transcribe_whisper_model）', () => {
  it('modelValue = params.model_size', () => {
    const w = mountParams({ model_size: 'large-v3' })
    const select = selects(w)[0]
    expect(select.props('modelValue')).toBe('large-v3')
  })

  it('選擇 → emit update:params 含 model_size', async () => {
    const w = mountParams({ model_size: 'medium' })
    const select = selects(w)[0]
    await select.vm.$emit('update:modelValue', 'small')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.model_size).toBe('small')
  })

  it('tool context：localStorage 有值且 params===defaults → 掛載時 seed patch', () => {
    localStorage.setItem('transcribe_whisper_model', 'large-v3')
    const w = mountParams({ model_size: 'medium' })
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.model_size).toBe('large-v3')
  })

  it('pipeline context：不讀 localStorage', () => {
    localStorage.setItem('transcribe_whisper_model', 'large-v3')
    const w = mountParams({ model_size: 'medium' }, 'pipeline')
    expect(w.emitted('update:params')).toBeUndefined()
  })
})

describe('TranscribeParams — output_format（txt/srt，vs subtitle 的 srt/vtt）', () => {
  it('modelValue = params.output_format（default "txt"）', () => {
    const w = mountParams({})
    const select = selects(w)[1]
    expect(select.props('modelValue')).toBe('txt')
  })

  it('切換 → emit update:params 含 output_format', async () => {
    const w = mountParams({})
    const select = selects(w)[1]
    await select.vm.$emit('update:modelValue', 'srt')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.output_format).toBe('srt')
  })
})

describe('TranscribeParams — vocal_separation', () => {
  it('切換 → commitPatch vocal_separation', async () => {
    const w = mountParams({ vocal_separation: false })
    // AppToggle[0]=TranslationOptionsPanel 內嵌「啟用翻譯」；[1]=summarize toggle；
    // [2]=vocal_separation（SettingsCollapsible 內第一個）。
    const toggle = w.findAllComponents(AppToggle)[2]
    await toggle.vm.$emit('update:modelValue', true)
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.vocal_separation).toBe(true)
  })
})

describe('TranscribeParams — WhisperAdvancedSettings v-model 寫回五個 params 欄位', () => {
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

describe('TranscribeParams — 翻譯 gate（獨立 translate bool，非 target_language 判準）', () => {
  it('未啟用時：TranslationOptionsPanel modelValue.enable_translation 對映 params.translate（false）', () => {
    const w = mountParams({ target_language: 'ja' }) // target_language 有值但 translate 未設 → 仍視為未啟用
    const panel = w.findComponent(TranslationOptionsPanel)
    const mv = panel.props('modelValue') as Record<string, unknown>
    expect(mv.enable_translation).toBe(false)
  })

  it('params.translate=true → modelValue.enable_translation=true', () => {
    const w = mountParams({ translate: true, target_language: 'en' })
    const panel = w.findComponent(TranslationOptionsPanel)
    const mv = panel.props('modelValue') as Record<string, unknown>
    expect(mv.enable_translation).toBe(true)
  })

  it('gate 開啟（enable_translation:true, target_language 空）→ translate:true + seed target_language "zh-TW"', async () => {
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
    expect(last.translate).toBe(true)
    expect(last.target_language).toBe('zh-TW')
    expect(last.keep_names).toBe(true)
    expect(last.translate_style).toBe('colloquial')
  })

  it('gate 開啟且已選本地翻譯模型 token → 展開 translate_model_family/size/quantization', async () => {
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
    expect(last.translate).toBe(true)
    expect(last.target_language).toBe('ja')
    expect(last.translate_model_family).toBe('gemma4')
    expect(last.translate_model_size).toBe('4b')
    expect(last.translate_quantization).toBe('Q4_K_M')
    expect(last.keep_names).toBe(false)
    expect(last.translate_style).toBe('formal')
  })

  it('gate 關閉 → translate:false + 清空 target_language/keep_names/translate_style/glossary/translate_* 七欄', async () => {
    const w = mountParams({
      translate: true,
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
    expect(last.translate).toBe(false)
    expect(last.target_language).toBeUndefined()
    expect(last.keep_names).toBeUndefined()
    expect(last.translate_style).toBeUndefined()
    expect(last.glossary).toBeUndefined()
    expect(last.translate_model_family).toBeUndefined()
    expect(last.translate_model_size).toBeUndefined()
    expect(last.translate_remote).toBeUndefined()
  })
})

describe('TranscribeParams — glossary text ↔ dict round trip', () => {
  it('params.glossary 為 dict → TranslationOptionsPanel modelValue.glossary_text 轉字串', () => {
    const w = mountParams({ translate: true, target_language: 'en', glossary: { Claude: 'Claude', 台北: 'Taipei' } })
    const panel = w.findComponent(TranslationOptionsPanel)
    const mv = panel.props('modelValue') as Record<string, unknown>
    expect(mv.glossary_text).toBe('Claude → Claude\n台北 → Taipei')
  })

  it('TranslationOptionsPanel emit glossary_text → 解析回 dict 寫入 params.glossary', async () => {
    const w = mountParams({ translate: true, target_language: 'en' })
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
})

describe('TranscribeParams — summarize toggle + picker（第三 composite，subtitle/summary 皆無）', () => {
  it('summarize=false → outline_model AppSelect 不渲染', () => {
    const w = mountParams({ summarize: false })
    // toggles: [0]=translate enable, [1]=summarize toggle
    // selects: whisper/output_format/(source_language pipeline 無)——不含 summarize select
    expect(selects(w)).toHaveLength(2)
  })

  it('切換 summarize toggle → commitPatch summarize', async () => {
    const w = mountParams({ summarize: false })
    const toggles = w.findAllComponents(AppToggle)
    const summarizeToggle = toggles[1] // [0]=translate enable, [1]=summarize
    await summarizeToggle.vm.$emit('update:modelValue', true)
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.summarize).toBe(true)
  })

  it('summarize=true → outline_model AppSelect 渲染，modelValue=encode token', () => {
    const w = mountParams({
      summarize: true,
      summarize_model_family: 'gemma4',
      summarize_model_size: '4b',
      summarize_quantization: 'Q4_K_M',
    })
    const selectList = selects(w)
    // whisper/output_format + summarize select（source_language 無 languages 時退文字輸入）
    expect(selectList).toHaveLength(3)
    const summarizeSelect = selectList[2]
    expect(summarizeSelect.props('modelValue')).toBe('gemma4:4b:Q4_K_M')
  })

  it('選擇本地 summarize 模型 → emit update:params 展開 summarize_model_family/size/quantization', async () => {
    const w = mountParams({ summarize: true })
    const summarizeSelect = selects(w)[2]
    await summarizeSelect.vm.$emit('update:modelValue', 'gemma4:12b:Q8_0')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.summarize_model_family).toBe('gemma4')
    expect(last.summarize_model_size).toBe('12b')
    expect(last.summarize_quantization).toBe('Q8_0')
    expect(last.summarize_remote).toBe(false)
  })

  it('選擇 remote summarize 模型 → emit update:params 展開 remote 四欄', async () => {
    const w = mountParams({ summarize: true })
    const summarizeSelect = selects(w)[2]
    await summarizeSelect.vm.$emit('update:modelValue', 'remote:openai:1:gpt-4o')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.summarize_remote).toBe(true)
    expect(last.summarize_provider).toBe('openai')
    expect(last.summarize_conn_id).toBe(1)
    expect(last.summarize_remote_model).toBe('gpt-4o')
  })

  it('tool context：localStorage 有值且 token===defaults → 掛載時 seed patch', () => {
    localStorage.setItem('transcribe_summarize_model', 'gemma4:12b:Q4_K_M')
    const w = mountParams({ summarize: true, summarize_model_family: 'gemma4', summarize_model_size: '4b' })
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.summarize_model_size).toBe('12b')
    expect(last.summarize_quantization).toBe('Q4_K_M')
  })

  it('fallback：清單載入含已下載項且目前 token 未對應任何選項 → 自動選中（tool context）', async () => {
    modelsState.models = [
      { family: 'gemma4', variant: '4b:Q4_K_M', label: 'Gemma4 4B', size_mb: 3000, downloaded: true, capabilities: ['text'] },
    ]
    const w = mountParams({ summarize: true })
    await flushPromises()
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.summarize_model_family).toBe('gemma4')
    expect(last.summarize_model_size).toBe('4b')
    expect(last.summarize_quantization).toBe('Q4_K_M')
  })
})

describe('TranscribeParams — composite 註冊（whisper_model／translate_model／summarize_model，covers 不重疊）', () => {
  function captureComposites() {
    const registered: AgentCompositeField[] = []
    const registerComposite = (c: AgentCompositeField) => {
      registered.push(c)
      return () => {}
    }
    return { registered, registerComposite }
  }

  it('三個 composite 皆註冊，covers 互不重疊', () => {
    const { registered, registerComposite } = captureComposites()
    mountParams({}, 'tool', registerComposite)
    expect(registered.map((c) => c.name).sort()).toEqual(['summarize_model', 'translate_model', 'whisper_model'])
    const allCovers = registered.flatMap((c) => c.covers)
    expect(new Set(allCovers).size).toBe(allCovers.length)
  })

  it('whisper_model composite：covers=[model_size]，get/set 正確', () => {
    const { registered, registerComposite } = captureComposites()
    mountParams({ model_size: 'small' }, 'tool', registerComposite)
    const whisper = registered.find((c) => c.name === 'whisper_model')!
    expect(whisper.covers).toEqual(['model_size'])
    expect(whisper.get({ model_size: 'large-v3' })).toBe('large-v3')
    expect(whisper.set('tiny')).toEqual({ model_size: 'tiny' })
  })

  it('translate_model composite：covers=七個 translate_* 欄位；gate(translate)關閉時 get 回空字串', () => {
    const { registered, registerComposite } = captureComposites()
    mountParams({}, 'tool', registerComposite)
    const translate = registered.find((c) => c.name === 'translate_model')!
    expect(translate.covers).toEqual([
      'translate_model_family', 'translate_model_size', 'translate_quantization',
      'translate_remote', 'translate_provider', 'translate_conn_id', 'translate_remote_model',
    ])
    expect(translate.get({ translate: false, translate_model_family: 'gemma4', translate_model_size: '4b' })).toBe('')
    expect(translate.get({})).toBe('')
  })

  it('translate_model composite：gate 開啟時 get 回 encode token；set 正確展開', () => {
    const { registered, registerComposite } = captureComposites()
    mountParams({}, 'tool', registerComposite)
    const translate = registered.find((c) => c.name === 'translate_model')!
    expect(translate.get({ translate: true, translate_model_family: 'gemma4', translate_model_size: '4b' })).toBe('gemma4:4b:')
    expect(translate.set('gemma4:4b:Q4_K_M')).toEqual({
      translate_remote: false,
      translate_provider: undefined,
      translate_conn_id: undefined,
      translate_remote_model: undefined,
      translate_model_family: 'gemma4',
      translate_model_size: '4b',
      translate_quantization: 'Q4_K_M',
    })
  })

  it('summarize_model composite：covers=七個 summarize_* 欄位；gate(summarize)關閉時 get 回空字串，開啟時回 encode token', () => {
    const { registered, registerComposite } = captureComposites()
    mountParams({}, 'tool', registerComposite)
    const summarize = registered.find((c) => c.name === 'summarize_model')!
    expect(summarize.covers).toEqual([
      'summarize_model_family', 'summarize_model_size', 'summarize_quantization',
      'summarize_remote', 'summarize_provider', 'summarize_conn_id', 'summarize_remote_model',
    ])
    expect(summarize.get({ summarize: false, summarize_model_family: 'gemma4', summarize_model_size: '4b' })).toBe('')
    expect(summarize.get({ summarize: true, summarize_model_family: 'gemma4', summarize_model_size: '4b' })).toBe('gemma4:4b:')
    expect(summarize.set('gemma4:4b:Q4_K_M')).toEqual({
      summarize_remote: false,
      summarize_provider: undefined,
      summarize_conn_id: undefined,
      summarize_remote_model: undefined,
      summarize_model_family: 'gemma4',
      summarize_model_size: '4b',
      summarize_quantization: 'Q4_K_M',
    })
  })
})
