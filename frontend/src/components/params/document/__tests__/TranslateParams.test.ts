/**
 * TranslateParams.vue 單測（統一參數元件案批 1 Task 1.5）。
 * 覆蓋：欄位佈局（無 advanced 分組，逐欄照搬舊 panel）、model picker 響應式衍生
 * （local/remote 互斥 commit）、glossary textarea↔dict 解析、pipeline context 停用
 * persisted seed、模型清單載入後 fallback 自動選第一個已下載模型。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

const modelsState = vi.hoisted(() => ({
  models: [] as Array<{ family: string; variant: string; label: string; size_mb: number; downloaded: boolean; capabilities?: string[] }>,
}))
const ensureLoadedMock = vi.hoisted(() => vi.fn())
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    byCapability: (cap: string) => modelsState.models.filter((m) => m.capabilities?.includes(cap)),
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

vi.mock('@/composables/useApi', () => ({
  apiFetch: vi.fn().mockResolvedValue({ ok: true, json: async () => [] }),
}))

import TranslateParams from '../TranslateParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'

function mountParams(params: Record<string, unknown>, context: 'tool' | 'pipeline' = 'tool') {
  return mount(TranslateParams, {
    props: { params, context, fileInfo: null },
    global: { mocks: { $t: (k: string) => k } },
  })
}

function findSelectByLabel(w: ReturnType<typeof mountParams>, labelKey: string) {
  const groups = w.findAll('.form-group')
  const g = groups.find((x) => x.find('label').text().includes(labelKey))
  return g?.findComponent(AppSelect)
}

beforeEach(() => {
  modelsState.models = []
  localStorage.clear()
  ensureLoadedMock.mockClear()
  remoteEnsureLoadedMock.mockClear()
})

describe('TranslateParams — 掛載時載入模型清單（review finding #1）', () => {
  it('mount 後 modelStore.ensureLoaded 與 remoteStore.ensureLoaded 皆被呼叫', () => {
    mountParams({ translate_style: 'colloquial', model_family: 'gemma4', model_size: '4b', remote: false })
    expect(ensureLoadedMock).toHaveBeenCalledTimes(1)
    expect(remoteEnsureLoadedMock).toHaveBeenCalledTimes(1)
  })
})

describe('TranslateParams — 佈局（逐欄照搬舊 panel，無 advanced 分組）', () => {
  it('無 SettingsCollapsible（舊 panel 全平鋪，無進階摺疊區）', () => {
    const w = mountParams({ translate_style: 'colloquial', model_family: 'gemma4', model_size: '4b', remote: false })
    expect(w.find('.settings-collapsible').exists()).toBe(false)
  })

  it('五個 form-group：model/source/target/style/glossary', () => {
    const w = mountParams({ translate_style: 'colloquial', model_family: 'gemma4', model_size: '4b', remote: false })
    expect(w.findAll('.form-group')).toHaveLength(5)
  })

  it('glossary textarea 存在且 rows=4', () => {
    const w = mountParams({})
    const ta = w.find('textarea.glossary-input')
    expect(ta.exists()).toBe(true)
    expect(ta.attributes('rows')).toBe('4')
  })
})

describe('TranslateParams — model picker 響應式衍生', () => {
  it('params 為 local 組合 → picker modelValue = family:size:quantization', () => {
    const w = mountParams({ model_family: 'gemma4', model_size: '4b', quantization: 'Q4_K_M', remote: false })
    const select = w.findAllComponents(AppSelect)[0]
    expect(select.props('modelValue')).toBe('gemma4:4b:Q4_K_M')
  })

  it('params 為 remote 組合 → picker modelValue = remote:provider:connId:modelId', () => {
    const w = mountParams({ remote: true, provider: 'openai', conn_id: 1, remote_model: 'gpt-4o' })
    const select = w.findAllComponents(AppSelect)[0]
    expect(select.props('modelValue')).toBe('remote:openai:1:gpt-4o')
  })

  it('選 local token → emit update:params 含七欄正確展開＋remote 側清空', async () => {
    const w = mountParams({ remote: true, provider: 'openai', conn_id: 1, remote_model: 'gpt-4o' })
    const select = w.findAllComponents(AppSelect)[0]
    await select.vm.$emit('update:modelValue', 'gemma4:12b:Q4_K_M')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.model_family).toBe('gemma4')
    expect(last.model_size).toBe('12b')
    expect(last.quantization).toBe('Q4_K_M')
    expect(last.remote).toBe(false)
    expect(last.provider).toBeUndefined()
    expect(last.conn_id).toBeUndefined()
    expect(last.remote_model).toBeUndefined()
  })

  it('選 remote token → emit update:params 含 remote 展開＋local 側清空', async () => {
    const w = mountParams({ model_family: 'gemma4', model_size: '4b', quantization: 'Q4_K_M', remote: false })
    const select = w.findAllComponents(AppSelect)[0]
    await select.vm.$emit('update:modelValue', 'remote:gemini:3:gemini-1.5-pro')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.remote).toBe(true)
    expect(last.provider).toBe('gemini')
    expect(last.conn_id).toBe(3)
    expect(last.remote_model).toBe('gemini-1.5-pro')
    expect(last.model_family).toBeUndefined()
    expect(last.model_size).toBeUndefined()
    expect(last.quantization).toBeUndefined()
  })
})

describe('TranslateParams — model picker fallback（清單載入後自動選第一個已下載模型）', () => {
  it('params 為 defaults（無 quantization）且本地清單載入後含一個已下載模型 → 自動選中並 emit', async () => {
    modelsState.models = [
      { family: 'gemma4', variant: '4b:Q4_K_M', label: 'Gemma4 4B', size_mb: 3000, downloaded: true, capabilities: ['text'] },
    ]
    const w = mountParams({ translate_style: 'colloquial', model_family: 'gemma4', model_size: '4b', remote: false })
    await flushPromises()
    const emitted = w.emitted('update:params')
    expect(emitted).toBeTruthy()
    const last = emitted![emitted!.length - 1][0] as Record<string, unknown>
    expect(last.quantization).toBe('Q4_K_M')
  })

  it('目前 token 已對應已知選項 → 不觸發 fallback（不多 emit）', async () => {
    modelsState.models = [
      { family: 'gemma4', variant: '4b:Q4_K_M', label: 'Gemma4 4B', size_mb: 3000, downloaded: true, capabilities: ['text'] },
    ]
    const w = mountParams({ model_family: 'gemma4', model_size: '4b', quantization: 'Q4_K_M', remote: false })
    await flushPromises()
    expect(w.emitted('update:params')).toBeFalsy()
  })
})

describe('TranslateParams — glossary textarea ↔ dict', () => {
  it('params.glossary 有值 → textarea 顯示為 "src → tgt" 每行一筆', () => {
    const w = mountParams({ glossary: { API: '應用程式介面', UI: '使用者介面' } })
    const ta = w.find('textarea.glossary-input')
    expect((ta.element as HTMLTextAreaElement).value).toBe('API → 應用程式介面\nUI → 使用者介面')
  })

  it('輸入 "原文 → 譯文" 換行分隔 → commit 時解析成 dict', async () => {
    const w = mountParams({})
    const ta = w.find('textarea.glossary-input')
    await ta.setValue('foo → bar\nbaz = qux')
    await ta.trigger('change')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.glossary).toEqual({ foo: 'bar', baz: 'qux' })
  })

  it('空白文字 → glossary undefined（非空物件）', async () => {
    const w = mountParams({ glossary: { a: 'b' } })
    const ta = w.find('textarea.glossary-input')
    await ta.setValue('   ')
    await ta.trigger('change')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.glossary).toBeUndefined()
  })

  it('非法行（無分隔符）容錯：整行跳過，其餘行照常解析', async () => {
    const w = mountParams({})
    const ta = w.find('textarea.glossary-input')
    await ta.setValue('this line has no separator\nfoo → bar')
    await ta.trigger('change')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.glossary).toEqual({ foo: 'bar' })
  })
})

describe('TranslateParams — 其餘欄位 commit', () => {
  it('切換來源語言 → commitPatch source_language', async () => {
    const w = mountParams({ source_language: 'en', target_language: 'zh-TW' })
    const select = findSelectByLabel(w, 'common.source_language')!
    await select.vm.$emit('update:modelValue', 'ja')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.source_language).toBe('ja')
    expect(last.target_language).toBe('zh-TW') // 其餘欄位透過 commitPatch 保留
  })

  it('切換翻譯風格 → commitPatch translate_style', async () => {
    const w = mountParams({ translate_style: 'colloquial' })
    const select = findSelectByLabel(w, 'document.translate.style')!
    await select.vm.$emit('update:modelValue', 'formal')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.translate_style).toBe('formal')
  })
})

describe('TranslateParams — pipeline context：無 persisted seed', () => {
  it('pipeline context 掛載不讀 localStorage（即使有殘留值也不套用 seed）', async () => {
    localStorage.setItem('doc_translate_model', 'gemma4:99b:Q4_K_M')
    const w = mountParams({ translate_style: 'colloquial', model_family: 'gemma4', model_size: '4b', remote: false }, 'pipeline')
    await flushPromises()
    // 無模型清單（models 空）情況下 fallback 也不會觸發；seed 應被 context!=='tool' 完全跳過
    const emitted = w.emitted('update:params')
    if (emitted) {
      const last = emitted[emitted.length - 1][0] as Record<string, unknown>
      expect(last.model_size).not.toBe('99b')
    }
  })

  it('pipeline context 選擇模型不寫入 localStorage', async () => {
    const w = mountParams({ remote: true, provider: 'openai', conn_id: 1, remote_model: 'gpt-4o' }, 'pipeline')
    const select = w.findAllComponents(AppSelect)[0]
    await select.vm.$emit('update:modelValue', 'gemma4:4b:Q4_K_M')
    expect(localStorage.getItem('doc_translate_model')).toBeNull()
  })
})

describe('TranslateParams — tool context：persisted seed（params 等於 defaults 時才套用）', () => {
  it('localStorage 有值且 params===defaults → 掛載時 seed patch', async () => {
    localStorage.setItem('doc_translate_model', 'remote:openai:1:gpt-4o')
    const w = mountParams({ translate_style: 'colloquial', model_family: 'gemma4', model_size: '4b', remote: false })
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.remote).toBe(true)
    expect(last.remote_model).toBe('gpt-4o')
  })

  it('params 已非 defaults（外部已指定模型）→ 不套用 seed，尊重現有 params', () => {
    localStorage.setItem('doc_translate_model', 'remote:openai:1:gpt-4o')
    const w = mountParams({ model_family: 'gemma4', model_size: '27b', quantization: 'Q4_K_M', remote: false })
    const emitted = w.emitted('update:params')
    if (emitted) {
      const last = emitted[emitted.length - 1][0] as Record<string, unknown>
      expect(last.model_size).not.toBe('27b') // 不應被 seed 覆蓋（如果有 emit，也不該是 seed 造成）
    }
  })

  it('review finding #4：本地清單已載入但 remoteStore 尚無此 token 時，fallback 不可蓋掉剛套用的 persisted remote seed', async () => {
    localStorage.setItem('doc_translate_model', 'remote:openai:1:gpt-4o')
    // 本地清單已載入且含一個已下載模型（模擬 seed 套用「同一輪」本地清單就緒的race）；
    // remoteStore mock 恆回傳空陣列 → merged options 此刻不含剛套用的 remote token。
    modelsState.models = [
      { family: 'gemma4', variant: '4b:Q4_K_M', label: 'Gemma4 4B', size_mb: 3000, downloaded: true, capabilities: ['text'] },
    ]
    const w = mountParams({ translate_style: 'colloquial', model_family: 'gemma4', model_size: '4b', remote: false })
    await flushPromises()
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.remote).toBe(true)
    expect(last.remote_model).toBe('gpt-4o')
    expect(last.model_family).toBeUndefined() // 不該被 fallback 蓋回本地 gemma4
  })
})
