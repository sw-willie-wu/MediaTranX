/**
 * LyricsParams.vue 單測（統一參數元件 spec §5；批 3 Task 3.5——批 3 收官，照
 * TranscribeParams.test.ts 裁剪）。覆蓋：欄位佈局（model/output_format 頂層＋
 * SettingsCollapsible 進階區僅 align）、whisper picker persisted seed、翻譯 gate（獨立
 * translate bool，非 target_language 判準）、glossary round trip、兩 composite 註冊
 * （covers 不重疊）。無 source_language/summarize/WhisperAdvancedSettings（lyrics 無此三者）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

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

import LyricsParams from '../LyricsParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'
import TranslationOptionsPanel from '@/components/video/TranslationOptionsPanel.vue'
import type { AgentCompositeField } from '../../types'

function mountParams(
  params: Record<string, unknown>,
  context: 'tool' | 'pipeline' = 'tool',
  registerComposite?: (c: AgentCompositeField) => () => void,
) {
  return mount(LyricsParams, {
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

describe('LyricsParams — 掛載時載入模型清單', () => {
  it('mount 後 modelStore/remoteStore.ensureLoaded 被呼叫', () => {
    mountParams({})
    expect(ensureLoadedMock).toHaveBeenCalled()
    expect(remoteEnsureLoadedMock).toHaveBeenCalled()
  })
})

describe('LyricsParams — 佈局（model/output_format 頂層，align 進階區，無 source_language/summarize）', () => {
  it('有 SettingsCollapsible 進階區', () => {
    const w = mountParams({})
    expect(w.findComponent(SettingsCollapsible).exists()).toBe(true)
  })

  it('TranslationOptionsPanel 內嵌，受控（有 modelValue prop）', () => {
    const w = mountParams({})
    const panel = w.findComponent(TranslationOptionsPanel)
    expect(panel.exists()).toBe(true)
    expect(panel.props('modelValue')).toBeDefined()
  })

  it('無 source_language 輸入欄（純 text input 不存在，因無此欄位）', () => {
    const w = mountParams({})
    expect(w.find('input[type="text"]').exists()).toBe(false)
  })

  it('恰有兩個 AppSelect（whisper + output_format），無 summarize select', () => {
    const w = mountParams({})
    expect(selects(w)).toHaveLength(2)
  })
})

describe('LyricsParams — whisper picker（欄位名 model_size；persist key lyrics_whisper_model）', () => {
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
    localStorage.setItem('lyrics_whisper_model', 'large-v3')
    const w = mountParams({ model_size: 'medium' })
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.model_size).toBe('large-v3')
  })

  it('pipeline context：不讀 localStorage', () => {
    localStorage.setItem('lyrics_whisper_model', 'large-v3')
    const w = mountParams({ model_size: 'medium' }, 'pipeline')
    expect(w.emitted('update:params')).toBeUndefined()
  })

  it('fallback：清單載入含已下載項且目前 token 未對應任何選項 → 自動選中（tool context）', () => {
    modelsState.models = [
      { family: 'whisper', variant: 'small', label: 'Small', size_mb: 500, downloaded: true, category: 'stt' },
    ]
    const w = mountParams({ model_size: 'nonexistent' })
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.model_size).toBe('small')
  })
})

describe('LyricsParams — output_format（lrc/txt）', () => {
  it('modelValue = params.output_format（default "lrc"）', () => {
    const w = mountParams({})
    const select = selects(w)[1]
    expect(select.props('modelValue')).toBe('lrc')
  })

  it('切換 → emit update:params 含 output_format', async () => {
    const w = mountParams({})
    const select = selects(w)[1]
    await select.vm.$emit('update:modelValue', 'txt')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.output_format).toBe('txt')
  })
})

describe('LyricsParams — align（advanced，v-model 化）', () => {
  it('切換 → commitPatch align', async () => {
    const w = mountParams({ align: false })
    // AppToggle[0]=TranslationOptionsPanel 內嵌「啟用翻譯」；[1]=align（SettingsCollapsible 內）。
    const toggle = w.findAllComponents(AppToggle)[1]
    await toggle.vm.$emit('update:modelValue', true)
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.align).toBe(true)
  })
})

describe('LyricsParams — 翻譯 gate（獨立 translate bool，非 target_language 判準）', () => {
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

describe('LyricsParams — glossary text ↔ dict round trip', () => {
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

describe('LyricsParams — composite 註冊（whisper_model／translate_model，covers 不重疊）', () => {
  function captureComposites() {
    const registered: AgentCompositeField[] = []
    const registerComposite = (c: AgentCompositeField) => {
      registered.push(c)
      return () => {}
    }
    return { registered, registerComposite }
  }

  it('兩個 composite 皆註冊，covers 互不重疊', () => {
    const { registered, registerComposite } = captureComposites()
    mountParams({}, 'tool', registerComposite)
    expect(registered.map((c) => c.name).sort()).toEqual(['translate_model', 'whisper_model'])
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
})
