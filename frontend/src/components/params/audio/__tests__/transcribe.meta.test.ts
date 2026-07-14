/**
 * audio.transcribe META 單測（統一參數元件 spec §4；批 3 Task 3.4——批 3 最大工具）。
 * 覆蓋 defaults/schema 不變量/佈局鐵則/buildSubmit 雙 gate（translate/summarize）剔欄矩陣/
 * modelRequirements 五道/encodeSubModelToken-decodeSubModelToken 純函式（roundtrip ×2 prefix）。
 */
import { describe, it, expect } from 'vitest'
import {
  META,
  WHISPER_SIZES,
  TRANSLATE_STYLES,
  TRANSLATE_FIELDS,
  SUMMARIZE_FIELDS,
  encodeSubModelToken,
  decodeSubModelToken,
} from '../transcribe.meta'

describe('audio.transcribe META', () => {
  it('defaults() 只含有 default 的欄位', () => {
    expect(META.defaults()).toEqual({
      model_size: 'medium',
      output_format: 'txt',
      translate: false,
      keep_names: true,
      translate_style: 'colloquial',
      summarize: false,
      vocal_separation: false,
      word_timestamps: false,
      condition_on_previous_text: true,
      min_silence_duration_ms: 200,
      vad_threshold: 0.3,
      align: false,
      translate_model_family: 'gemma4',
      translate_model_size: '4b',
      translate_remote: false,
      summarize_model_family: 'gemma4',
      summarize_model_size: '4b',
      summarize_remote: false,
    })
  })

  it('schema 不變量：每個 enum 欄位 default ∈ options', () => {
    for (const f of META.schema) {
      if (f.type === 'enum' && f.default !== undefined) {
        expect(f.options ?? [], f.name).toContain(f.default)
      }
    }
  })

  it('schema 含全 29 欄（file_id/suppress_results 除外）', () => {
    const names = META.schema.map((f) => f.name)
    expect(names).toHaveLength(29)
    expect(names).not.toContain('file_id')
    expect(names).not.toContain('suppress_results')
    expect(new Set(names).size).toBe(names.length)
    expect(META.schema.find((f) => f.name === 'glossary')?.type).toBe('dict')
  })

  it('佈局鐵則：model_size/source_language/output_format/translate 主欄/summarize 主欄非 advanced；vocal_separation+whisper 進階五欄與 translate_*/summarize_* 動態模型系皆 advanced', () => {
    const topLevel = [
      'model_size', 'source_language', 'output_format',
      'translate', 'target_language', 'keep_names', 'translate_style', 'glossary',
      'summarize',
    ]
    const advanced = [
      'vocal_separation', 'word_timestamps', 'condition_on_previous_text', 'min_silence_duration_ms', 'vad_threshold', 'align',
      ...TRANSLATE_FIELDS, ...SUMMARIZE_FIELDS,
    ]
    for (const name of topLevel) {
      expect(META.schema.find((f) => f.name === name)?.advanced, name).not.toBe(true)
    }
    for (const name of advanced) {
      expect(META.schema.find((f) => f.name === name)?.advanced, name).toBe(true)
    }
  })

  it('visibleWhen：translate_* 系欄位（含 target_language/keep_names/translate_style/glossary）僅 translate===true 顯示；summarize_* 僅 summarize===true', () => {
    const translateGated = ['target_language', 'keep_names', 'translate_style', 'glossary', ...TRANSLATE_FIELDS]
    for (const name of translateGated) {
      const f = META.schema.find((x) => x.name === name)!
      expect(f.visibleWhen?.({ translate: true }), name).toBe(true)
      expect(f.visibleWhen?.({ translate: false }), name).toBe(false)
    }
    for (const name of SUMMARIZE_FIELDS) {
      const f = META.schema.find((x) => x.name === name)!
      expect(f.visibleWhen?.({ summarize: true }), name).toBe(true)
      expect(f.visibleWhen?.({ summarize: false }), name).toBe(false)
    }
  })

  it('WHISPER_SIZES / TRANSLATE_STYLES / TRANSLATE_FIELDS / SUMMARIZE_FIELDS 常數形狀', () => {
    expect(WHISPER_SIZES).toEqual(['tiny', 'base', 'small', 'medium', 'large-v3'])
    expect(TRANSLATE_STYLES).toEqual(['colloquial', 'formal', 'literal'])
    expect(TRANSLATE_FIELDS).toEqual([
      'translate_model_family', 'translate_model_size', 'translate_quantization',
      'translate_remote', 'translate_provider', 'translate_conn_id', 'translate_remote_model',
    ])
    expect(SUMMARIZE_FIELDS).toEqual([
      'summarize_model_family', 'summarize_model_size', 'summarize_quantization',
      'summarize_remote', 'summarize_provider', 'summarize_conn_id', 'summarize_remote_model',
    ])
  })

  it('multiSelect: true（沿舊 AudioView.handleMultiExecute 支援批次）', () => {
    expect(META.multiSelect).toBe(true)
  })

  it('agentExecuteLabel 沿舊字串；agentRequiresConfirm 不設（退回 host 預設 true）', () => {
    expect(META.agentExecuteLabel).toBe('panel.transcribe.execute')
    expect(META.agentRequiresConfirm).toBeUndefined()
  })

  it('persistedModelFields = model_size + 七個 translate_* + 七個 summarize_* 欄', () => {
    expect(META.persistedModelFields).toEqual(['model_size', ...TRANSLATE_FIELDS, ...SUMMARIZE_FIELDS])
  })

  describe('buildSubmit — 雙 gate 剔欄矩陣', () => {
    it('translate=false, summarize=false → payload 不含任一組子欄，translate/summarize 恆送 false', () => {
      const spec = META.buildSubmit!({ model_size: 'medium', output_format: 'txt' })
      expect(spec.payload).toEqual({
        model_size: 'medium',
        output_format: 'txt',
        vocal_separation: false,
        word_timestamps: false,
        align: false,
        condition_on_previous_text: true,
        min_silence_duration_ms: 200,
        vad_threshold: 0.3,
        translate: false,
        summarize: false,
      })
      expect(spec.apiPath).toBe('/audio/transcribe')
      expect(spec.taskType).toBe('audio.transcribe')
      expect(spec.labelKey).toBe('audio.transcribe.task_label')
    })

    it('source_language 空字串/未設 → 不含 source_language 鍵；有值才送', () => {
      expect(META.buildSubmit!({}).payload.source_language).toBeUndefined()
      expect(META.buildSubmit!({ source_language: 'en' }).payload.source_language).toBe('en')
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

    it('summarize=true → summarize:true 送出 + 本地模型子欄（family/size fallback gemma4/4b）', () => {
      const spec = META.buildSubmit!({ summarize: true })
      expect(spec.payload.summarize).toBe(true)
      expect(spec.payload.summarize_model_family).toBe('gemma4')
      expect(spec.payload.summarize_model_size).toBe('4b')
      expect(spec.payload.summarize_remote).toBeUndefined()
    })

    it('summarize=true + summarize_quantization 有值才送', () => {
      expect(META.buildSubmit!({ summarize: true }).payload.summarize_quantization).toBeUndefined()
      expect(META.buildSubmit!({ summarize: true, summarize_quantization: 'Q4_K_M' }).payload.summarize_quantization).toBe('Q4_K_M')
    })

    it('summarize_remote===true → 走 remote 四欄，不含 summarize_model_family/size/quantization', () => {
      const spec = META.buildSubmit!({
        summarize: true,
        summarize_remote: true,
        summarize_provider: 'gemini',
        summarize_conn_id: 2,
        summarize_remote_model: 'gemini-1.5-pro',
      })
      expect(spec.payload.summarize_remote).toBe(true)
      expect(spec.payload.summarize_provider).toBe('gemini')
      expect(spec.payload.summarize_conn_id).toBe(2)
      expect(spec.payload.summarize_remote_model).toBe('gemini-1.5-pro')
      expect(spec.payload.summarize_model_family).toBeUndefined()
      expect(spec.payload.summarize_model_size).toBeUndefined()
    })

    it('translate=true 且 summarize=true 同時成立 → 兩組子欄皆送（獨立 gate，互不影響）', () => {
      const spec = META.buildSubmit!({
        translate: true, target_language: 'zh-TW',
        summarize: true,
      })
      expect(spec.payload.translate).toBe(true)
      expect(spec.payload.target_language).toBe('zh-TW')
      expect(spec.payload.summarize).toBe(true)
      expect(spec.payload.summarize_model_family).toBe('gemma4')
    })

    it('vocal_separation/word_timestamps/align 等布林欄位恆送（無論兩個 gate 狀態）', () => {
      const spec = META.buildSubmit!({ vocal_separation: true, word_timestamps: true, align: true })
      expect(spec.payload.vocal_separation).toBe(true)
      expect(spec.payload.word_timestamps).toBe(true)
      expect(spec.payload.align).toBe(true)
    })

    it('payload 不含 file_id（host 注入）', () => {
      const spec = META.buildSubmit!({ translate: true, target_language: 'en' })
      expect(spec.payload).not.toHaveProperty('file_id')
    })
  })

  describe('modelRequirements — 五道（whisper→demucs→align→translate→summarize）', () => {
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

    it('translate=true（無 target_language 判準，vs buildSubmit 不同）→ 追加 translate requirement', () => {
      const reqs = META.modelRequirements!({ model_size: 'medium', translate: true })
      expect(reqs).toContainEqual({ slot: 'translate', family: 'gemma4', size: '4b' })
    })

    it('translate=true 但 target_language 空 → 仍追加 translate requirement（preflight 無 targetLanguage 判準，逐字鏡射舊碼）', () => {
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

    it('summarize=true → 追加 summarize requirement（family/size fallback gemma4/4b）', () => {
      const reqs = META.modelRequirements!({ summarize: true })
      expect(reqs).toContainEqual({ slot: 'summarize', family: 'gemma4', size: '4b' })
    })

    it('summarize=true 且 summarize_remote=true → 不追加 summarize requirement', () => {
      const reqs = META.modelRequirements!({ summarize: true, summarize_remote: true })
      expect(reqs!.some((r) => r.slot === 'summarize')).toBe(false)
    })

    it('summarize 未設/false → 不追加 summarize requirement', () => {
      expect(META.modelRequirements!({})!.some((r) => r.slot === 'summarize')).toBe(false)
    })

    it('summarize requirement 含 quantization（有值時才帶 key）', () => {
      const reqs = META.modelRequirements!({ summarize: true, summarize_quantization: 'Q8_0' })
      const req = reqs!.find((r) => r.slot === 'summarize')
      expect(req).toEqual({ slot: 'summarize', family: 'gemma4', size: '4b', quantization: 'Q8_0' })
    })

    it('無任何進階選項 → 只有 whisper 一筆', () => {
      expect(META.modelRequirements!({ model_size: 'medium' })).toHaveLength(1)
    })

    it('translate=true 且 summarize=true 同時成立 → 五筆需求全到齊（whisper/demucs/align/translate/summarize）', () => {
      const reqs = META.modelRequirements!({
        model_size: 'medium', vocal_separation: true, align: true, translate: true, summarize: true,
      })
      expect(reqs!.map((r) => r.slot)).toEqual(['whisper', 'separate', 'align', 'translate', 'summarize'])
    })
  })
})

describe('encodeSubModelToken / decodeSubModelToken（參數化，prefix=translate/summarize）', () => {
  for (const prefix of ['translate', 'summarize'] as const) {
    describe(`prefix=${prefix}`, () => {
      it('local：family:size:quantization', () => {
        expect(encodeSubModelToken({
          [`${prefix}_remote`]: false, [`${prefix}_model_family`]: 'gemma4', [`${prefix}_model_size`]: '4b', [`${prefix}_quantization`]: 'Q4_K_M',
        }, prefix)).toBe('gemma4:4b:Q4_K_M')
      })

      it('local，quantization 未設 → 尾端空段', () => {
        expect(encodeSubModelToken({ [`${prefix}_remote`]: false, [`${prefix}_model_family`]: 'gemma4', [`${prefix}_model_size`]: '4b' }, prefix))
          .toBe('gemma4:4b:')
      })

      it('remote：remote:provider:connId:modelId', () => {
        expect(encodeSubModelToken({
          [`${prefix}_remote`]: true, [`${prefix}_provider`]: 'openai', [`${prefix}_conn_id`]: 1, [`${prefix}_remote_model`]: 'gpt-4o',
        }, prefix)).toBe('remote:openai:1:gpt-4o')
      })

      it('family/size 皆空（未設） → 回傳空字串，不回傳 "::"', () => {
        expect(encodeSubModelToken({ [`${prefix}_remote`]: false }, prefix)).toBe('')
      })

      it('family/size 皆空但 quantization 有值（不合法狀態）→ 仍視為空', () => {
        expect(encodeSubModelToken({ [`${prefix}_remote`]: false, [`${prefix}_quantization`]: 'Q4_K_M' }, prefix)).toBe('')
      })

      it('decode local token → 七欄完整展開，remote 側清空(undefined)', () => {
        expect(decodeSubModelToken('gemma4:4b:Q4_K_M', prefix)).toEqual({
          [`${prefix}_remote`]: false,
          [`${prefix}_provider`]: undefined,
          [`${prefix}_conn_id`]: undefined,
          [`${prefix}_remote_model`]: undefined,
          [`${prefix}_model_family`]: 'gemma4',
          [`${prefix}_model_size`]: '4b',
          [`${prefix}_quantization`]: 'Q4_K_M',
        })
      })

      it('decode remote token → 七欄完整展開，local 側清空(undefined)', () => {
        expect(decodeSubModelToken('remote:openai:1:gpt-4o', prefix)).toEqual({
          [`${prefix}_remote`]: true,
          [`${prefix}_provider`]: 'openai',
          [`${prefix}_conn_id`]: 1,
          [`${prefix}_remote_model`]: 'gpt-4o',
          [`${prefix}_model_family`]: undefined,
          [`${prefix}_model_size`]: undefined,
          [`${prefix}_quantization`]: undefined,
        })
      })

      it('remote token，modelId 含冒號 → 用 slice(3).join 還原完整 modelId', () => {
        const patch = decodeSubModelToken('remote:ollama:2:llama3.1:8b', prefix)
        expect(patch[`${prefix}_remote_model`]).toBe('llama3.1:8b')
      })

      it('roundtrip：encode(decode(token)) === token（local/remote）', () => {
        expect(encodeSubModelToken(decodeSubModelToken('gemma4:12b:Q4_K_M', prefix), prefix)).toBe('gemma4:12b:Q4_K_M')
        expect(encodeSubModelToken(decodeSubModelToken('remote:gemini:3:gemini-1.5-pro', prefix), prefix)).toBe('remote:gemini:3:gemini-1.5-pro')
      })

      it('local↔remote 互斥：patch 套用後另一側六欄被 undefined 覆蓋掉，不留殘值', () => {
        const priorParams: Record<string, unknown> = {
          [`${prefix}_remote`]: false, [`${prefix}_model_family`]: 'gemma4', [`${prefix}_model_size`]: '4b', [`${prefix}_quantization`]: 'Q4_K_M',
        }
        const merged = { ...priorParams, ...decodeSubModelToken('remote:openai:1:gpt-4o', prefix) }
        expect(merged[`${prefix}_model_family`]).toBeUndefined()
        expect(merged[`${prefix}_model_size`]).toBeUndefined()
        expect(merged[`${prefix}_quantization`]).toBeUndefined()
        expect(merged[`${prefix}_remote`]).toBe(true)
      })
    })
  }
})
