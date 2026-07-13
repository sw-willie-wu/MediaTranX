/**
 * video.subtitle META 單測（統一參數元件 spec §4；批 2 Task 2.5——例外殼工具）。
 * 覆蓋 defaults/schema 不變量/buildSubmit 翻譯 gate 剔欄/modelRequirements 條件/
 * encode-decodeTranslateToken 純函式（roundtrip、local/remote 互斥、清除語意）。
 */
import { describe, it, expect } from 'vitest'
import {
  META,
  WHISPER_SIZES,
  TRANSLATE_STYLES,
  TRANSLATE_FIELDS,
  encodeTranslateToken,
  decodeTranslateToken,
} from '../subtitle.meta'

describe('video.subtitle META', () => {
  it('defaults() 只含有 default 的欄位', () => {
    expect(META.defaults()).toEqual({
      model_size: 'medium',
      output_format: 'srt',
      keep_names: true,
      translate_style: 'colloquial',
      translate_model_family: 'gemma4',
      translate_model_size: '4b',
      translate_remote: false,
      word_timestamps: false,
      condition_on_previous_text: true,
      min_silence_duration_ms: 200,
      vad_threshold: 0.3,
      align: false,
      vocal_separation: false,
    })
  })

  it('schema 不變量：每個 enum 欄位 default ∈ options', () => {
    for (const f of META.schema) {
      if (f.type === 'enum' && f.default !== undefined) {
        expect(f.options ?? [], f.name).toContain(f.default)
      }
    }
  })

  it('schema 含全 20 欄（file_id/suppress_results 除外，glossary 已加回）', () => {
    const names = META.schema.map((f) => f.name)
    expect(names).toEqual([
      'source_language', 'model_size', 'output_format',
      'target_language', 'keep_names', 'translate_style', 'glossary',
      'translate_model_family', 'translate_model_size', 'translate_quantization',
      'translate_remote', 'translate_provider', 'translate_conn_id', 'translate_remote_model',
      'word_timestamps', 'condition_on_previous_text', 'min_silence_duration_ms', 'vad_threshold',
      'align', 'vocal_separation',
    ])
    expect(names).toHaveLength(20)
    expect(META.schema.find((f) => f.name === 'glossary')?.type).toBe('dict')
    expect(names).not.toContain('file_id')
    expect(names).not.toContain('suppress_results')
  })

  it('佈局鐵則：source_language/model_size/output_format 與翻譯主欄位（target_language/keep_names/translate_style/glossary）非 advanced；動態模型系與 Whisper 進階欄位皆 advanced', () => {
    const topLevel = ['source_language', 'model_size', 'output_format', 'target_language', 'keep_names', 'translate_style', 'glossary']
    const advanced = [
      'translate_model_family', 'translate_model_size', 'translate_quantization',
      'translate_remote', 'translate_provider', 'translate_conn_id', 'translate_remote_model',
      'word_timestamps', 'condition_on_previous_text', 'min_silence_duration_ms', 'vad_threshold',
      'align', 'vocal_separation',
    ]
    for (const name of topLevel) {
      expect(META.schema.find((f) => f.name === name)?.advanced, name).not.toBe(true)
    }
    for (const name of advanced) {
      expect(META.schema.find((f) => f.name === name)?.advanced, name).toBe(true)
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

  it('multiSelect false（殼硬編 isMultiSelect 恆 false，m16）', () => {
    expect(META.multiSelect).toBe(false)
  })

  it('persistedModelFields = model_size + 七個 translate_* 欄', () => {
    expect(META.persistedModelFields).toEqual(['model_size', ...TRANSLATE_FIELDS])
  })

  describe('buildSubmit — 翻譯 gate（target_language 非空字串代表已啟用）', () => {
    it('target_language 未設 → payload 不含任何 translate_*/keep_names/translate_style/glossary', () => {
      const spec = META.buildSubmit!({ model_size: 'medium', output_format: 'srt' })
      expect(spec.payload).toEqual({
        model_size: 'medium',
        output_format: 'srt',
        vocal_separation: false,
        word_timestamps: false,
        align: false,
        condition_on_previous_text: true,
        min_silence_duration_ms: 200,
        vad_threshold: 0.3,
      })
      expect(spec.labelKey).toBe('video.subtitle.task_label')
      expect(spec.apiPath).toBe('/video/subtitle/generate')
      expect(spec.taskType).toBe('subtitle/generate')
    })

    it('target_language 空字串 → 視同未啟用（不送 translate_*）', () => {
      const spec = META.buildSubmit!({ target_language: '', model_size: 'medium' })
      expect(spec.payload.target_language).toBeUndefined()
      expect(spec.labelKey).toBe('video.subtitle.task_label')
    })

    it('source_language 空字串/未設 → 不含 source_language 鍵；有值才送', () => {
      expect(META.buildSubmit!({}).payload.source_language).toBeUndefined()
      expect(META.buildSubmit!({ source_language: 'en' }).payload.source_language).toBe('en')
    })

    it('target_language 有值＋本地模型 → 含 translate_model_family/size + keep_names/translate_style，labelKey 帶 translate', () => {
      const spec = META.buildSubmit!({
        target_language: 'zh-TW',
        translate_model_family: 'gemma4',
        translate_model_size: '4b',
        keep_names: false,
        translate_style: 'formal',
      })
      expect(spec.payload.target_language).toBe('zh-TW')
      expect(spec.payload.translate_model_family).toBe('gemma4')
      expect(spec.payload.translate_model_size).toBe('4b')
      expect(spec.payload.translate_remote).toBeUndefined()
      expect(spec.payload.keep_names).toBe(false)
      expect(spec.payload.translate_style).toBe('formal')
      expect(spec.labelKey).toBe('video.subtitle.task_label_with_translate')
    })

    it('translate_quantization 未設/空字串 → 不進 payload；有值才送', () => {
      expect(META.buildSubmit!({ target_language: 'zh-TW' }).payload.translate_quantization).toBeUndefined()
      expect(META.buildSubmit!({ target_language: 'zh-TW', translate_quantization: '' }).payload.translate_quantization).toBeUndefined()
      expect(META.buildSubmit!({ target_language: 'zh-TW', translate_quantization: 'Q4_K_M' }).payload.translate_quantization).toBe('Q4_K_M')
    })

    it('translate_remote===true → 走 remote 四欄，不含 translate_model_family/size/quantization', () => {
      const spec = META.buildSubmit!({
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
      expect(META.buildSubmit!({ target_language: 'en', glossary: {} }).payload.glossary).toBeUndefined()
      const g = { Claude: 'Claude' }
      expect(META.buildSubmit!({ target_language: 'en', glossary: g }).payload.glossary).toEqual(g)
    })

    it('vocal_separation/word_timestamps/align 等布林欄位恆送（無論翻譯 gate 狀態）', () => {
      const spec = META.buildSubmit!({ vocal_separation: true, word_timestamps: true, align: true })
      expect(spec.payload.vocal_separation).toBe(true)
      expect(spec.payload.word_timestamps).toBe(true)
      expect(spec.payload.align).toBe(true)
    })

    it('payload 不含 file_id（host/殼注入）', () => {
      const spec = META.buildSubmit!({ target_language: 'en' })
      expect(spec.payload).not.toHaveProperty('file_id')
    })
  })

  describe('modelRequirements', () => {
    it('恆含 whisper（slot=whisper，variant=model_size，categories=[stt]）', () => {
      expect(META.modelRequirements!({ model_size: 'large-v3' })).toEqual([
        { slot: 'whisper', variant: 'large-v3', categories: ['stt'] },
      ])
    })

    it('vocal_separation=true → 追加 demucs requirement', () => {
      const reqs = META.modelRequirements!({ model_size: 'medium', vocal_separation: true })
      expect(reqs).toContainEqual({ slot: 'separate', variant: 'htdemucs_6s', family: 'demucs', categories: ['separate'] })
    })

    it('align=true → 追加 align requirement（categories-only）', () => {
      const reqs = META.modelRequirements!({ model_size: 'medium', align: true })
      expect(reqs).toContainEqual({ slot: 'align', categories: ['alignment'] })
    })

    it('target_language 有值且非 remote → 追加 translate requirement（family/size，quant 有值才傳）', () => {
      const reqs = META.modelRequirements!({
        model_size: 'medium',
        target_language: 'zh-TW',
        translate_model_family: 'gemma4',
        translate_model_size: '4b',
      })
      expect(reqs).toContainEqual({ slot: 'translate', family: 'gemma4', size: '4b' })
    })

    it('M2：translate_model_family/size 未設 → requirement 補 buildSubmit 同款 fallback（gemma4/4b）', () => {
      const reqs = META.modelRequirements!({ target_language: 'zh-TW' })
      expect(reqs).toContainEqual({ slot: 'translate', family: 'gemma4', size: '4b' })
    })

    it('translate requirement 含 quantization（有值時才帶 key）', () => {
      const reqs = META.modelRequirements!({
        target_language: 'zh-TW',
        translate_model_family: 'gemma4',
        translate_model_size: '4b',
        translate_quantization: 'Q4_K_M',
      })
      const translateReq = reqs!.find((r) => r.slot === 'translate')
      expect(translateReq).toEqual({ slot: 'translate', family: 'gemma4', size: '4b', quantization: 'Q4_K_M' })
    })

    it('target_language 有值但 translate_remote=true → 不追加 translate requirement（雲端免下載）', () => {
      const reqs = META.modelRequirements!({ target_language: 'zh-TW', translate_remote: true })
      expect(reqs!.some((r) => r.slot === 'translate')).toBe(false)
    })

    it('target_language 空 → 不追加 translate requirement', () => {
      const reqs = META.modelRequirements!({ target_language: '' })
      expect(reqs!.some((r) => r.slot === 'translate')).toBe(false)
    })

    it('無任何進階選項 → 只有 whisper 一筆', () => {
      expect(META.modelRequirements!({ model_size: 'medium' })).toHaveLength(1)
    })
  })
})

describe('encodeTranslateToken', () => {
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
    expect(encodeTranslateToken({ translate_remote: true, translate_provider: 'openai', translate_conn_id: 1, translate_remote_model: 'gpt-4o' }))
      .toBe('remote:openai:1:gpt-4o')
  })

  it('M1：family/size 皆空（未設） → 回傳空字串，不回傳 "::"', () => {
    expect(encodeTranslateToken({ translate_remote: false })).toBe('')
  })

  it('M1：family/size 皆空字串 → 回傳空字串，不回傳 "::"', () => {
    expect(encodeTranslateToken({ translate_remote: false, translate_model_family: '', translate_model_size: '' })).toBe('')
  })

  it('M1：family/size 皆空但 quantization 有值（不合法狀態）→ 仍視為空，回傳空字串', () => {
    expect(encodeTranslateToken({ translate_remote: false, translate_quantization: 'Q4_K_M' })).toBe('')
  })
})

describe('decodeTranslateToken', () => {
  it('local token → 七欄完整展開，remote 側清空(undefined)', () => {
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

  it('remote token → 七欄完整展開，local 側清空(undefined)', () => {
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
