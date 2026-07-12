/**
 * audio.lyrics META 單測（統一參數元件 spec §4；批 3 Task 3.5——批 3 收官，照
 * transcribe.meta.test.ts 裁剪）。覆蓋 defaults/schema 不變量/佈局鐵則/buildSubmit
 * 剔欄矩陣/modelRequirements 四道（demucs 無條件）/encodeTranslateToken-decodeTranslateToken
 * 純函式 roundtrip。
 */
import { describe, it, expect } from 'vitest'
import {
  META,
  WHISPER_SIZES,
  TRANSLATE_STYLES,
  TRANSLATE_FIELDS,
  encodeTranslateToken,
  decodeTranslateToken,
} from '../lyrics.meta'

describe('audio.lyrics META', () => {
  it('defaults() 只含有 default 的欄位', () => {
    expect(META.defaults()).toEqual({
      model_size: 'medium',
      output_format: 'lrc',
      translate: false,
      keep_names: true,
      translate_style: 'colloquial',
      align: false,
      translate_model_family: 'gemma4',
      translate_model_size: '4b',
      translate_remote: false,
    })
  })

  it('schema 不變量：每個 enum 欄位 default ∈ options', () => {
    for (const f of META.schema) {
      if (f.type === 'enum' && f.default !== undefined) {
        expect(f.options ?? [], f.name).toContain(f.default)
      }
    }
  })

  it('schema 含全 15 欄（file_id/suppress_results 除外），無 source_language/vocal_separation/summarize', () => {
    const names = META.schema.map((f) => f.name)
    expect(names).toHaveLength(15)
    expect(names).not.toContain('file_id')
    expect(names).not.toContain('suppress_results')
    expect(names).not.toContain('source_language')
    expect(names).not.toContain('vocal_separation')
    expect(names).not.toContain('summarize')
    expect(new Set(names).size).toBe(names.length)
    expect(META.schema.find((f) => f.name === 'glossary')?.type).toBe('dict')
  })

  it('佈局鐵則：model_size/output_format/translate 主欄非 advanced；align+translate_* 動態模型系皆 advanced', () => {
    const topLevel = [
      'model_size', 'output_format',
      'translate', 'target_language', 'keep_names', 'translate_style', 'glossary',
    ]
    const advanced = ['align', ...TRANSLATE_FIELDS]
    for (const name of topLevel) {
      expect(META.schema.find((f) => f.name === name)?.advanced, name).not.toBe(true)
    }
    for (const name of advanced) {
      expect(META.schema.find((f) => f.name === name)?.advanced, name).toBe(true)
    }
  })

  it('visibleWhen：translate_* 系欄位（含 target_language/keep_names/translate_style/glossary）僅 translate===true 顯示', () => {
    const translateGated = ['target_language', 'keep_names', 'translate_style', 'glossary', ...TRANSLATE_FIELDS]
    for (const name of translateGated) {
      const f = META.schema.find((x) => x.name === name)!
      expect(f.visibleWhen?.({ translate: true }), name).toBe(true)
      expect(f.visibleWhen?.({ translate: false }), name).toBe(false)
    }
  })

  it('WHISPER_SIZES / TRANSLATE_STYLES / TRANSLATE_FIELDS 常數形狀', () => {
    expect(WHISPER_SIZES).toEqual(['tiny', 'base', 'small', 'medium', 'large-v3'])
    expect(TRANSLATE_STYLES).toEqual(['colloquial', 'formal', 'literal'])
    expect(TRANSLATE_FIELDS).toEqual([
      'translate_model_family', 'translate_model_size', 'translate_quantization',
      'translate_remote', 'translate_provider', 'translate_conn_id', 'translate_remote_model',
    ])
  })

  it('multiSelect: true（沿舊 AudioView.handleMultiExecute lyrics case 支援批次）', () => {
    expect(META.multiSelect).toBe(true)
  })

  it('agentExecuteLabel/agentRequiresConfirm 皆不設（舊 panel 無 agentSchema，退回 host 預設 labelKey/true）', () => {
    expect(META.agentExecuteLabel).toBeUndefined()
    expect(META.agentRequiresConfirm).toBeUndefined()
    expect(META.labelKey).toBe('audio.lyrics.task_label')
  })

  it('persistedModelFields = model_size + 七個 translate_* 欄', () => {
    expect(META.persistedModelFields).toEqual(['model_size', ...TRANSLATE_FIELDS])
  })

  describe('buildSubmit — 剔欄矩陣', () => {
    it('translate=false → payload 不含 translate_* 子欄，translate 恆送 false', () => {
      const spec = META.buildSubmit!({ model_size: 'medium', output_format: 'lrc' })
      expect(spec.payload).toEqual({
        model_size: 'medium',
        output_format: 'lrc',
        align: false,
        translate: false,
      })
      expect(spec.apiPath).toBe('/audio/lyrics')
      expect(spec.taskType).toBe('audio.lyrics')
      expect(spec.labelKey).toBe('audio.lyrics.task_label')
    })

    it('translate=true 但 target_language 空 → translate:true 仍送，但不含 target_language/子欄（雙重判準）', () => {
      const spec = META.buildSubmit!({ translate: true, target_language: '' })
      expect(spec.payload.translate).toBe(true)
      expect(spec.payload.target_language).toBeUndefined()
      expect(spec.payload.translate_model_family).toBeUndefined()
      expect(spec.payload.keep_names).toBeUndefined()
    })

    it('translate=true 且 target_language 有值 + 本地模型 → 含 translate_model_family/size + keep_names/translate_style', () => {
      const spec = META.buildSubmit!({
        translate: true,
        target_language: 'zh-TW',
        translate_model_family: 'gemma4',
        translate_model_size: '4b',
        keep_names: false,
        translate_style: 'formal',
      })
      expect(spec.payload.translate).toBe(true)
      expect(spec.payload.target_language).toBe('zh-TW')
      expect(spec.payload.translate_model_family).toBe('gemma4')
      expect(spec.payload.translate_model_size).toBe('4b')
      expect(spec.payload.translate_remote).toBeUndefined()
      expect(spec.payload.keep_names).toBe(false)
      expect(spec.payload.translate_style).toBe('formal')
    })

    it('translate_quantization 未設/空字串 → 不進 payload；有值才送', () => {
      const base = { translate: true, target_language: 'zh-TW' }
      expect(META.buildSubmit!(base).payload.translate_quantization).toBeUndefined()
      expect(META.buildSubmit!({ ...base, translate_quantization: '' }).payload.translate_quantization).toBeUndefined()
      expect(META.buildSubmit!({ ...base, translate_quantization: 'Q4_K_M' }).payload.translate_quantization).toBe('Q4_K_M')
    })

    it('translate_remote===true → 走 remote 四欄，不含 translate_model_family/size/quantization', () => {
      const spec = META.buildSubmit!({
        translate: true,
        target_language: 'ja',
        translate_remote: true,
        translate_provider: 'openai',
        translate_conn_id: 1,
        translate_remote_model: 'gpt-4o',
      })
      expect(spec.payload.translate_remote).toBe(true)
      expect(spec.payload.translate_provider).toBe('openai')
      expect(spec.payload.translate_conn_id).toBe(1)
      expect(spec.payload.translate_remote_model).toBe('gpt-4o')
      expect(spec.payload.translate_model_family).toBeUndefined()
      expect(spec.payload.translate_model_size).toBeUndefined()
    })

    it('glossary 空 dict → 不進 payload；非空 dict → 原樣送', () => {
      expect(META.buildSubmit!({ translate: true, target_language: 'en', glossary: {} }).payload.glossary).toBeUndefined()
      const g = { Claude: 'Claude' }
      expect(META.buildSubmit!({ translate: true, target_language: 'en', glossary: g }).payload.glossary).toEqual(g)
    })

    it('align 恆送（無論 translate 狀態）', () => {
      const spec = META.buildSubmit!({ align: true })
      expect(spec.payload.align).toBe(true)
    })

    it('payload 不含 file_id（host 注入）', () => {
      const spec = META.buildSubmit!({ translate: true, target_language: 'en' })
      expect(spec.payload).not.toHaveProperty('file_id')
    })
  })

  describe('modelRequirements — 四道（whisper→demucs(無條件)→align→translate）', () => {
    it('恆含 whisper + demucs（demucs 無條件，vs transcribe 需 vocal_separation===true）', () => {
      expect(META.modelRequirements!({ model_size: 'large-v3' })).toEqual([
        { slot: 'whisper', variant: 'large-v3', categories: ['stt'] },
        { slot: 'separate', variant: 'htdemucs_6s', family: 'demucs', categories: ['separate'] },
      ])
    })

    it('align=true → 追加 align requirement（categories-only）', () => {
      const reqs = META.modelRequirements!({ model_size: 'medium', align: true })
      expect(reqs).toContainEqual({ slot: 'align', categories: ['alignment'] })
    })

    it('align 未設/false → 不追加 align requirement', () => {
      expect(META.modelRequirements!({})!.some((r) => r.slot === 'align')).toBe(false)
    })

    it('translate=true（無 target_language 判準，vs buildSubmit 不同）→ 追加 translate requirement', () => {
      const reqs = META.modelRequirements!({ model_size: 'medium', translate: true })
      expect(reqs).toContainEqual({ slot: 'translate', family: 'gemma4', size: '4b' })
    })

    it('translate=true 但 target_language 空 → 仍追加 translate requirement（preflight 無 targetLanguage 判準）', () => {
      const reqs = META.modelRequirements!({ translate: true, target_language: '' })
      expect(reqs!.some((r) => r.slot === 'translate')).toBe(true)
    })

    it('translate=true 且 translate_remote=true → 不追加 translate requirement（雲端免下載）', () => {
      const reqs = META.modelRequirements!({ translate: true, translate_remote: true })
      expect(reqs!.some((r) => r.slot === 'translate')).toBe(false)
    })

    it('translate 未設/false → 不追加 translate requirement', () => {
      expect(META.modelRequirements!({})!.some((r) => r.slot === 'translate')).toBe(false)
    })

    it('translate requirement 含 quantization（有值時才帶 key）', () => {
      const reqs = META.modelRequirements!({ translate: true, translate_quantization: 'Q4_K_M' })
      const req = reqs!.find((r) => r.slot === 'translate')
      expect(req).toEqual({ slot: 'translate', family: 'gemma4', size: '4b', quantization: 'Q4_K_M' })
    })

    it('無任何進階選項 → 只有 whisper+demucs 兩筆', () => {
      expect(META.modelRequirements!({ model_size: 'medium' })).toHaveLength(2)
    })

    it('align=true 且 translate=true 同時成立 → 四筆需求全到齊（whisper/demucs/align/translate）', () => {
      const reqs = META.modelRequirements!({
        model_size: 'medium', align: true, translate: true,
      })
      expect(reqs!.map((r) => r.slot)).toEqual(['whisper', 'separate', 'align', 'translate'])
    })
  })
})

describe('encodeTranslateToken / decodeTranslateToken', () => {
  it('local：family:size:quantization', () => {
    expect(encodeTranslateToken({
      translate_remote: false, translate_model_family: 'gemma4', translate_model_size: '4b', translate_quantization: 'Q4_K_M',
    })).toBe('gemma4:4b:Q4_K_M')
  })

  it('local，quantization 未設 → 尾端空段', () => {
    expect(encodeTranslateToken({ translate_remote: false, translate_model_family: 'gemma4', translate_model_size: '4b' }))
      .toBe('gemma4:4b:')
  })

  it('remote：remote:provider:connId:modelId', () => {
    expect(encodeTranslateToken({
      translate_remote: true, translate_provider: 'openai', translate_conn_id: 1, translate_remote_model: 'gpt-4o',
    })).toBe('remote:openai:1:gpt-4o')
  })

  it('family/size 皆空（未設） → 回傳空字串，不回傳 "::"', () => {
    expect(encodeTranslateToken({ translate_remote: false })).toBe('')
  })

  it('family/size 皆空但 quantization 有值（不合法狀態）→ 仍視為空', () => {
    expect(encodeTranslateToken({ translate_remote: false, translate_quantization: 'Q4_K_M' })).toBe('')
  })

  it('decode local token → 七欄完整展開，remote 側清空(undefined)', () => {
    expect(decodeTranslateToken('gemma4:4b:Q4_K_M')).toEqual({
      translate_remote: false,
      translate_provider: undefined,
      translate_conn_id: undefined,
      translate_remote_model: undefined,
      translate_model_family: 'gemma4',
      translate_model_size: '4b',
      translate_quantization: 'Q4_K_M',
    })
  })

  it('decode remote token → 七欄完整展開，local 側清空(undefined)', () => {
    expect(decodeTranslateToken('remote:openai:1:gpt-4o')).toEqual({
      translate_remote: true,
      translate_provider: 'openai',
      translate_conn_id: 1,
      translate_remote_model: 'gpt-4o',
      translate_model_family: undefined,
      translate_model_size: undefined,
      translate_quantization: undefined,
    })
  })

  it('remote token，modelId 含冒號 → 用 slice(3).join 還原完整 modelId', () => {
    const patch = decodeTranslateToken('remote:ollama:2:llama3.1:8b')
    expect(patch.translate_remote_model).toBe('llama3.1:8b')
  })

  it('roundtrip：encode(decode(token)) === token（local/remote）', () => {
    expect(encodeTranslateToken(decodeTranslateToken('gemma4:12b:Q4_K_M'))).toBe('gemma4:12b:Q4_K_M')
    expect(encodeTranslateToken(decodeTranslateToken('remote:gemini:3:gemini-1.5-pro'))).toBe('remote:gemini:3:gemini-1.5-pro')
  })

  it('local↔remote 互斥：patch 套用後另一側六欄被 undefined 覆蓋掉，不留殘值', () => {
    const priorParams: Record<string, unknown> = {
      translate_remote: false, translate_model_family: 'gemma4', translate_model_size: '4b', translate_quantization: 'Q4_K_M',
    }
    const merged = { ...priorParams, ...decodeTranslateToken('remote:openai:1:gpt-4o') }
    expect(merged.translate_model_family).toBeUndefined()
    expect(merged.translate_model_size).toBeUndefined()
    expect(merged.translate_quantization).toBeUndefined()
    expect(merged.translate_remote).toBe(true)
  })
})
