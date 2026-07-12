/**
 * SummaryParams.vue 單測（統一參數元件案批 2 Task 2.4）。
 * 覆蓋：欄位佈局（頂層 4 個 form-group＋SettingsCollapsible 進階區含 language/
 * vocal_separation/WhisperAdvancedSettings）、三個 model picker 響應式衍生與 commit、
 * VLM 清空語意、summary_mode/vocal_separation commit、WhisperAdvancedSettings v-model
 * 寫回 params、pipeline context 不 seed/不持久化、tool context persisted seed 生效。
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
  }),
}))

const remoteEnsureLoadedMock = vi.hoisted(() => vi.fn())
vi.mock('@/stores/remoteModels', () => ({
  useRemoteModelStore: () => ({
    byCapability: () => [] as unknown[],
    ensureLoaded: remoteEnsureLoadedMock,
  }),
}))

import SummaryParams from '../SummaryParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import WhisperAdvancedSettings from '@/components/video/WhisperAdvancedSettings.vue'

function mountParams(params: Record<string, unknown>, context: 'tool' | 'pipeline' = 'tool') {
  return mount(SummaryParams, {
    props: { params, context, fileInfo: null },
    global: { mocks: { $t: (k: string) => k } },
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
})

describe('SummaryParams — 掛載時載入模型清單', () => {
  it('mount 後 modelStore.ensureLoaded 與 remoteStore.ensureLoaded 皆被呼叫', () => {
    mountParams({})
    expect(ensureLoadedMock).toHaveBeenCalledTimes(1)
    expect(remoteEnsureLoadedMock).toHaveBeenCalledTimes(1)
  })
})

describe('SummaryParams — 佈局（沿舊 VideoSummaryPanel：mode/whisper/llm/vlm 頂層，language/vocal_separation/WhisperAdvanced 進階區）', () => {
  it('頂層四個 form-group：summary_mode/whisper/llm/vlm', () => {
    const w = mountParams({})
    // SettingsCollapsible 內容預設收合，DOM 仍會渲染（依 SettingsCollapsible 實作，此處只斷言頂層四個 select）
    expect(selects(w).length).toBeGreaterThanOrEqual(4)
  })

  it('有 SettingsCollapsible 進階區', () => {
    const w = mountParams({})
    expect(w.find('.settings-collapsible').exists()).toBe(true)
  })

  it('WhisperAdvancedSettings 以 embedded=true 掛載', () => {
    const w = mountParams({})
    const whisperAdv = w.findComponent(WhisperAdvancedSettings)
    expect(whisperAdv.exists()).toBe(true)
    expect(whisperAdv.props('embedded')).toBe(true)
  })
})

describe('SummaryParams — whisper picker', () => {
  it('modelValue = params.whisper_model_size', () => {
    const w = mountParams({ whisper_model_size: 'large-v3' })
    const select = selects(w)[1] // [0]=summary_mode, [1]=whisper
    expect(select.props('modelValue')).toBe('large-v3')
  })

  it('選擇 → emit update:params 含 whisper_model_size', async () => {
    const w = mountParams({ whisper_model_size: 'medium' })
    const select = selects(w)[1]
    await select.vm.$emit('update:modelValue', 'small')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.whisper_model_size).toBe('small')
  })
})

describe('SummaryParams — llm picker（六欄 composite，無 quantization）', () => {
  it('local 組合 → picker modelValue = family:size', () => {
    const w = mountParams({ llm_model_family: 'gemma4', llm_model_size: '9b', llm_remote: false })
    const select = selects(w)[2] // [2]=llm
    expect(select.props('modelValue')).toBe('gemma4:9b')
  })

  it('remote 組合 → picker modelValue = remote:provider:connId:modelId', () => {
    const w = mountParams({ llm_remote: true, llm_provider: 'openai', llm_conn_id: 1, llm_remote_model: 'gpt-4o' })
    const select = selects(w)[2]
    expect(select.props('modelValue')).toBe('remote:openai:1:gpt-4o')
  })

  it('選 local token → emit 六欄正確展開，remote 側清空', async () => {
    const w = mountParams({ llm_remote: true, llm_provider: 'openai', llm_conn_id: 1, llm_remote_model: 'gpt-4o' })
    const select = selects(w)[2]
    await select.vm.$emit('update:modelValue', 'gemma4:9b')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.llm_model_family).toBe('gemma4')
    expect(last.llm_model_size).toBe('9b')
    expect(last.llm_remote).toBe(false)
    expect(last.llm_provider).toBeUndefined()
    expect(last.llm_conn_id).toBeUndefined()
    expect(last.llm_remote_model).toBeUndefined()
  })

  it('選 remote token → emit remote 展開，local 側清空', async () => {
    const w = mountParams({ llm_model_family: 'gemma4', llm_model_size: '9b', llm_remote: false })
    const select = selects(w)[2]
    await select.vm.$emit('update:modelValue', 'remote:gemini:3:gemini-1.5-pro')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.llm_remote).toBe(true)
    expect(last.llm_provider).toBe('gemini')
    expect(last.llm_conn_id).toBe(3)
    expect(last.llm_remote_model).toBe('gemini-1.5-pro')
    expect(last.llm_model_family).toBeUndefined()
    expect(last.llm_model_size).toBeUndefined()
  })
})

describe('SummaryParams — vlm picker（同 llm，多一個 "" 不使用哨兵）', () => {
  it('vlm 全空 → picker modelValue = ""', () => {
    const w = mountParams({})
    const select = selects(w)[3] // [3]=vlm
    expect(select.props('modelValue')).toBe('')
  })

  it('options 含 "" 哨兵（video.summary.vlm_none）', () => {
    const w = mountParams({})
    const select = selects(w)[3]
    const opts = select.props('options') as Array<{ value: string; label: string }>
    expect(opts.some((o) => o.value === '' && o.label === 'video.summary.vlm_none')).toBe(true)
  })

  it('選 "" → emit 六欄全清（不使用 VLM）', async () => {
    const w = mountParams({ vlm_model_family: 'qwen3vl', vlm_model_size: '8b', vlm_remote: false })
    const select = selects(w)[3]
    await select.vm.$emit('update:modelValue', '')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.vlm_model_family).toBeUndefined()
    expect(last.vlm_model_size).toBeUndefined()
    expect(last.vlm_remote).toBe(false)
  })

  it('選具體本地 token → emit 六欄展開', async () => {
    const w = mountParams({})
    const select = selects(w)[3]
    await select.vm.$emit('update:modelValue', 'qwen3vl:8b')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.vlm_model_family).toBe('qwen3vl')
    expect(last.vlm_model_size).toBe('8b')
  })
})

describe('SummaryParams — summary_mode / vocal_separation commit', () => {
  it('切換 summary_mode → commitPatch summary_mode', async () => {
    const w = mountParams({ summary_mode: 'bullets' })
    const select = selects(w)[0]
    await select.vm.$emit('update:modelValue', 'narrative')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.summary_mode).toBe('narrative')
  })

  it('切換 vocal_separation → commitPatch vocal_separation', async () => {
    const w = mountParams({ vocal_separation: false })
    const toggle = w.findComponent(AppToggle)
    await toggle.vm.$emit('update:modelValue', true)
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.vocal_separation).toBe(true)
  })
})

describe('SummaryParams — WhisperAdvancedSettings v-model 寫回五個 params 欄位', () => {
  it('modelValue 反映目前 params 五欄', () => {
    const w = mountParams({
      word_timestamps: true,
      align: false,
      condition_on_previous_text: false,
      min_silence_duration_ms: 500,
      vad_threshold: 0.5,
    })
    const whisperAdv = w.findComponent(WhisperAdvancedSettings)
    expect(whisperAdv.props('modelValue')).toEqual({
      word_timestamps: true,
      align: false,
      condition_on_previous_text: false,
      min_silence_duration_ms: 500,
      vad_threshold: 0.5,
    })
  })

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
    expect(last.condition_on_previous_text).toBe(false)
    expect(last.min_silence_duration_ms).toBe(1000)
    expect(last.vad_threshold).toBe(0.7)
  })
})

describe('SummaryParams — pipeline context：無 persisted seed', () => {
  it('pipeline context 掛載不讀 localStorage（殘留值不套用）', async () => {
    localStorage.setItem('video_summary_whisper_model', 'large-v3')
    const w = mountParams({}, 'pipeline')
    await flushPromises()
    const select = selects(w)[1]
    expect(select.props('modelValue')).not.toBe('large-v3')
  })

  it('pipeline context 選擇模型不寫入 localStorage', async () => {
    const w = mountParams({}, 'pipeline')
    const select = selects(w)[1]
    await select.vm.$emit('update:modelValue', 'small')
    expect(localStorage.getItem('video_summary_whisper_model')).toBeNull()
  })
})

describe('SummaryParams — tool context：persisted seed（params 等於 defaults 時才套用）', () => {
  it('whisper：localStorage 有值且 params===defaults → 掛載時 seed patch', () => {
    localStorage.setItem('video_summary_whisper_model', 'large-v3')
    const w = mountParams({ whisper_model_size: 'medium' })
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.whisper_model_size).toBe('large-v3')
  })

  it('llm：localStorage 有值且 params 為空（等同 default token）→ 掛載時 seed patch', () => {
    localStorage.setItem('video_summary_llm_model', 'remote:openai:1:gpt-4o')
    const w = mountParams({})
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.llm_remote).toBe(true)
    expect(last.llm_remote_model).toBe('gpt-4o')
  })
})

describe('SummaryParams — whisper/llm fallback 自動選第一個已下載模型（tool context）', () => {
  it('whisper 清單載入後含已下載項且目前 token 未對應任何選項 → 自動選中', async () => {
    modelsState.models = [
      { family: 'whisper', variant: 'small', label: 'Small', size_mb: 500, downloaded: true, category: 'stt' },
    ]
    const w = mountParams({ whisper_model_size: 'medium' })
    await flushPromises()
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.whisper_model_size).toBe('small')
  })

  it('llm 清單載入後含已下載項且目前 token 為空 → 自動選中', async () => {
    modelsState.models = [
      { family: 'gemma4', variant: '9b:Q4_K_M', label: 'Gemma4 9B', size_mb: 3000, downloaded: true, capabilities: ['text'] },
    ]
    const w = mountParams({})
    await flushPromises()
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.llm_model_family).toBe('gemma4')
    expect(last.llm_model_size).toBe('9b')
  })

  it('vlm 清單載入後不會自動選中任何模型（"" 哨兵恆在選項內，維持不使用）', async () => {
    modelsState.models = [
      { family: 'qwen3vl', variant: '8b:Q4_K_M', label: 'Qwen3VL 8B', size_mb: 4000, downloaded: true, capabilities: ['vision'] },
    ]
    const w = mountParams({})
    await flushPromises()
    const select = selects(w)[3]
    expect(select.props('modelValue')).toBe('')
  })
})
