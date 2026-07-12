/**
 * document.translate META 單測（統一參數元件 spec §4；批 1 Task 1.5）。
 * 覆蓋 defaults/modelRequirement/schema 不變量 ＋ encode/decodeModelToken 純函式
 * （roundtrip、local/remote 互斥、清除語意）。
 */
import { describe, it, expect } from 'vitest'
import { META, MODEL_FIELDS, TRANSLATE_STYLES, encodeModelToken, decodeModelToken } from '../translate.meta'

describe('document.translate META', () => {
  it('defaults() 只含有 default 的欄位', () => {
    expect(META.defaults()).toEqual({
      translate_style: 'colloquial',
      model_family: 'gemma4',
      model_size: '4b',
      remote: false,
    })
  })

  it('schema 不變量：每個 enum 欄位 default ∈ options', () => {
    for (const f of META.schema) {
      if (f.type === 'enum' && f.default !== undefined) {
        expect(f.options ?? [], f.name).toContain(f.default)
      }
    }
  })

  it('schema 含全七個 model 欄位＋glossary(dict)＋語言/風格欄位', () => {
    const names = META.schema.map((f) => f.name)
    expect(names).toEqual([
      'source_language', 'target_language', 'translate_style', 'glossary',
      'model_family', 'model_size', 'quantization', 'remote', 'provider', 'conn_id', 'remote_model',
    ])
    expect(META.schema.find((f) => f.name === 'glossary')?.type).toBe('dict')
  })

  it('TRANSLATE_STYLES / MODEL_FIELDS 常數形狀', () => {
    expect(TRANSLATE_STYLES).toEqual(['colloquial', 'formal', 'literal'])
    expect(MODEL_FIELDS).toEqual([
      'model_family', 'model_size', 'quantization', 'remote', 'provider', 'conn_id', 'remote_model',
    ])
  })

  it('multiSelect true（沿舊 DocumentView.handleMultiExecute 支援批次）', () => {
    expect(META.multiSelect).toBe(true)
  })

  it('persistedModelFields 宣告全七欄', () => {
    expect(META.persistedModelFields).toEqual([
      'model_family', 'model_size', 'quantization', 'remote', 'provider', 'conn_id', 'remote_model',
    ])
  })

  describe('modelRequirement', () => {
    it('remote===true → null（雲端模型免下載守門）', () => {
      expect(META.modelRequirement!({ remote: true, provider: 'openai', conn_id: 1, remote_model: 'gpt-4o' })).toBeNull()
    })

    it('remote===false（或未設）→ { slot, family, size, quantization }', () => {
      expect(META.modelRequirement!({ model_family: 'gemma4', model_size: '4b', quantization: 'Q4_K_M' })).toEqual({
        slot: 'translate', family: 'gemma4', size: '4b', quantization: 'Q4_K_M',
      })
    })

    it('quantization 未設 → undefined（非拋錯）', () => {
      expect(META.modelRequirement!({ model_family: 'gemma4', model_size: '4b' })).toEqual({
        slot: 'translate', family: 'gemma4', size: '4b', quantization: undefined,
      })
    })
  })
})

describe('encodeModelToken', () => {
  it('local：family:size:quantization', () => {
    expect(encodeModelToken({ remote: false, model_family: 'gemma4', model_size: '4b', quantization: 'Q4_K_M' }))
      .toBe('gemma4:4b:Q4_K_M')
  })

  it('local，quantization 未設 → 尾端空段', () => {
    expect(encodeModelToken({ remote: false, model_family: 'gemma4', model_size: '4b' }))
      .toBe('gemma4:4b:')
  })

  it('remote：remote:provider:connId:modelId', () => {
    expect(encodeModelToken({ remote: true, provider: 'openai', conn_id: 1, remote_model: 'gpt-4o' }))
      .toBe('remote:openai:1:gpt-4o')
  })

  it('remote，modelId 含冒號時原樣保留（split 後段落全保留在 encode 輸入端，無需特殊處理）', () => {
    expect(encodeModelToken({ remote: true, provider: 'ollama', conn_id: 2, remote_model: 'llama3.1:8b' }))
      .toBe('remote:ollama:2:llama3.1:8b')
  })
})

describe('decodeModelToken', () => {
  it('local token → 七欄完整展開，remote 側清空(undefined)', () => {
    expect(decodeModelToken('gemma4:4b:Q4_K_M')).toEqual({
      remote: false,
      provider: undefined,
      conn_id: undefined,
      remote_model: undefined,
      model_family: 'gemma4',
      model_size: '4b',
      quantization: 'Q4_K_M',
    })
  })

  it('remote token → 七欄完整展開，local 側清空(undefined)', () => {
    expect(decodeModelToken('remote:openai:1:gpt-4o')).toEqual({
      remote: true,
      provider: 'openai',
      conn_id: 1,
      remote_model: 'gpt-4o',
      model_family: undefined,
      model_size: undefined,
      quantization: undefined,
    })
  })

  it('remote token，modelId 含冒號 → 用 slice(3).join 還原完整 modelId', () => {
    const patch = decodeModelToken('remote:ollama:2:llama3.1:8b')
    expect(patch.remote_model).toBe('llama3.1:8b')
    expect(patch.provider).toBe('ollama')
    expect(patch.conn_id).toBe(2)
  })

  it('local token，quantization 空段 → quantization undefined（非空字串）', () => {
    expect(decodeModelToken('gemma4:4b:').quantization).toBeUndefined()
  })

  it('roundtrip：encode(decode(token)) === token（local）', () => {
    const token = 'gemma4:12b:Q4_K_M'
    expect(encodeModelToken(decodeModelToken(token))).toBe(token)
  })

  it('roundtrip：encode(decode(token)) === token（remote）', () => {
    const token = 'remote:gemini:3:gemini-1.5-pro'
    expect(encodeModelToken(decodeModelToken(token))).toBe(token)
  })

  it('local→remote 互斥：decode remote token 的 patch 套用後，local 三欄必須從 params 中被 undefined 覆蓋掉（不留殘值）', () => {
    const priorParams: Record<string, unknown> = { remote: false, model_family: 'gemma4', model_size: '4b', quantization: 'Q4_K_M' }
    const patch = decodeModelToken('remote:openai:1:gpt-4o')
    const merged = { ...priorParams, ...patch }
    expect(merged.model_family).toBeUndefined()
    expect(merged.model_size).toBeUndefined()
    expect(merged.quantization).toBeUndefined()
    expect(merged.remote).toBe(true)
  })

  it('remote→local 互斥：decode local token 的 patch 套用後，remote 三欄必須從 params 中被 undefined 覆蓋掉（不留殘值）', () => {
    const priorParams: Record<string, unknown> = { remote: true, provider: 'openai', conn_id: 1, remote_model: 'gpt-4o' }
    const patch = decodeModelToken('gemma4:4b:Q4_K_M')
    const merged = { ...priorParams, ...patch }
    expect(merged.provider).toBeUndefined()
    expect(merged.conn_id).toBeUndefined()
    expect(merged.remote_model).toBeUndefined()
    expect(merged.remote).toBe(false)
  })

  it('JSON.stringify 後 undefined 鍵不殘留（送後端前的實際樣貌）', () => {
    const patch = decodeModelToken('remote:openai:1:gpt-4o')
    const merged = { remote: false, model_family: 'gemma4', model_size: '4b', quantization: 'Q4_K_M', ...patch }
    const serialized = JSON.parse(JSON.stringify(merged))
    expect(serialized).toEqual({ remote: true, provider: 'openai', conn_id: 1, remote_model: 'gpt-4o' })
  })
})
