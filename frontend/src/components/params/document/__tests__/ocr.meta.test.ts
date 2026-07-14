/**
 * document.ocr META 單測（統一參數元件 spec §4；批 4 Task 4.4）。
 * 覆蓋 defaults/modelRequirement（remote 短路、family fallback）/downloadFormatField/
 * encodeModelToken/decodeModelToken（local/remote 互斥覆蓋）。
 */
import { describe, it, expect } from 'vitest'
import { META, encodeModelToken, decodeModelToken, MODEL_FIELDS } from '../ocr.meta'

describe('document.ocr META', () => {
  it('defaults() 含 output_format/model_size（其餘無 default 不出現）', () => {
    expect(META.defaults()).toEqual({
      output_format: 'md',
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

  it('toolKey/apiPath/labelKey/taskType', () => {
    expect(META.toolKey).toBe('document.ocr')
    expect(META.apiPath).toBe('/document/ocr')
    expect(META.labelKey).toBe('document.ocr.task_label')
    expect(META.taskType).toBe('document.ocr')
  })

  it('agentExecuteLabel = panel.doc_ocr.execute（沿舊 DocumentOcrPanel）', () => {
    expect(META.agentExecuteLabel).toBe('panel.doc_ocr.execute')
  })

  it('downloadFormatField = output_format（TextPreviewModal 契約）', () => {
    expect(META.downloadFormatField).toBe('output_format')
  })

  it('multiSelect true；persistedModelFields = 七個 model 欄', () => {
    expect(META.multiSelect).toBe(true)
    expect(META.persistedModelFields).toEqual([...MODEL_FIELDS])
  })

  describe('modelRequirement', () => {
    it('remote=true → null（雲端不需本地模型下載）', () => {
      expect(META.modelRequirement!({ remote: true, model_family: 'qwen3vl', model_size: '4b' })).toBeNull()
    })

    it('remote=false 且 model_family 有值 → 原樣傳遞', () => {
      expect(META.modelRequirement!({ remote: false, model_family: 'gemma4', model_size: '9b', quantization: 'Q4_K_M' })).toEqual({
        slot: 'ocr', family: 'gemma4', size: '9b', quantization: 'Q4_K_M',
      })
    })

    it('model_family 未定義（後端 None）→ fallback qwen3vl（DEFAULT_VLM_MODEL 鏡射）', () => {
      expect(META.modelRequirement!({ remote: false })).toEqual({
        slot: 'ocr', family: 'qwen3vl', size: '4b', quantization: undefined,
      })
    })

    it('model_size 未定義 → fallback 4b', () => {
      expect(META.modelRequirement!({ remote: false, model_family: 'gemma4' })).toEqual({
        slot: 'ocr', family: 'gemma4', size: '4b', quantization: undefined,
      })
    })
  })

  it('無 buildSubmit（沿舊 getParams 原樣透傳，無分流需求）', () => {
    expect(META.buildSubmit).toBeUndefined()
  })
})

describe('document.ocr encodeModelToken/decodeModelToken', () => {
  it('local：family:size（quantization 不進 token）', () => {
    expect(encodeModelToken({ remote: false, model_family: 'gemma4', model_size: '9b', quantization: 'Q4_K_M' })).toBe('gemma4:9b')
  })

  it('remote：remote:provider:connId:modelId', () => {
    expect(encodeModelToken({ remote: true, provider: 'openai', conn_id: 3, remote_model: 'gpt-4o' })).toBe('remote:openai:3:gpt-4o')
  })

  it('decode local token → 七欄 patch，remote 側清空', () => {
    expect(decodeModelToken('gemma4:9b')).toEqual({
      remote: false,
      provider: undefined,
      conn_id: undefined,
      remote_model: undefined,
      model_family: 'gemma4',
      model_size: '9b',
      quantization: undefined,
    })
  })

  it('decode remote token → 七欄 patch，local 側清空', () => {
    expect(decodeModelToken('remote:openai:3:gpt-4o')).toEqual({
      remote: true,
      provider: 'openai',
      conn_id: 3,
      remote_model: 'gpt-4o',
      model_family: undefined,
      model_size: undefined,
      quantization: undefined,
    })
  })

  it('decode remote token 的 modelId 含冒號 → slice(3).join(":") 保留完整', () => {
    expect(decodeModelToken('remote:ollama:1:qwen2.5:7b').remote_model).toBe('qwen2.5:7b')
  })

  it('roundtrip：encode(decode(token)) === token（local）', () => {
    const token = 'gemma4:9b'
    expect(encodeModelToken(decodeModelToken(token))).toBe(token)
  })

  it('roundtrip：encode(decode(token)) === token（remote）', () => {
    const token = 'remote:openai:3:gpt-4o'
    expect(encodeModelToken(decodeModelToken(token))).toBe(token)
  })
})
