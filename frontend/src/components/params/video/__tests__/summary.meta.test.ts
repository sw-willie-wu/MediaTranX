/**
 * video.summary META 單測（統一參數元件 spec §4；批 2 Task 2.4）。
 * 覆蓋 defaults/modelRequirements 五道條件開關/token roundtrip/schema 不變量。
 */
import { describe, it, expect } from 'vitest'
import { META, encodeModelToken, decodeModelToken } from '../summary.meta'

describe('video.summary META', () => {
  it('defaults() 含全部有 default 的欄位', () => {
    expect(META.defaults()).toEqual({
      summary_mode: 'bullets',
      language: 'zh-TW',
      whisper_model_size: 'medium',
      llm_remote: false,
      vlm_remote: false,
      vocal_separation: false,
      align: false,
      word_timestamps: false,
      condition_on_previous_text: true,
      min_silence_duration_ms: 200,
      vad_threshold: 0.3,
    })
  })

  it('schema 不變量：每個 enum 欄位 default ∈ options', () => {
    for (const f of META.schema) {
      if (f.type === 'enum' && f.default !== undefined) {
        expect(f.options ?? [], f.name).toContain(f.default)
      }
    }
  })

  // 後端 VideoSummaryRequest 逐欄核對（scripts/backend/app/api/routes/video/summary.py）：
  // 扣 file_id/suppress_results 後實際 21 欄（brief 文件標「22 欄」為筆誤，此處以後端原始碼
  // 逐欄核對為準——llm_*6/language1/vlm_*6/whisper_model_size1/vocal_separation1/align1/
  // word_timestamps1/condition_on_previous_text1/min_silence_duration_ms1/vad_threshold1/
  // summary_mode1 = 21）。
  it('schema 全集 21 欄（後端 VideoSummaryRequest 扣 file_id/suppress_results）', () => {
    expect(META.schema).toHaveLength(21)
  })

  it('agentExecuteLabel 沿舊 VideoSummaryPanel.agentSchema.execute.label（與 labelKey 不同）', () => {
    expect(META.agentExecuteLabel).toBe('panel.summary.execute')
    expect(META.agentExecuteLabel).not.toBe(META.labelKey)
  })

  it('multiSelect true（舊 VideoView.handleMultiExecute 已支援批次）', () => {
    expect(META.multiSelect).toBe(true)
  })

  it('persistedModelFields = whisper_model_size + 六個 llm_* + 六個 vlm_*（13 欄，不含 summary_mode）', () => {
    expect(META.persistedModelFields).toEqual([
      'whisper_model_size',
      'llm_model_family', 'llm_model_size', 'llm_remote', 'llm_provider', 'llm_conn_id', 'llm_remote_model',
      'vlm_model_family', 'vlm_model_size', 'vlm_remote', 'vlm_provider', 'vlm_conn_id', 'vlm_remote_model',
    ])
  })

  describe('modelRequirements（五道 guard，順序同舊 VideoSummaryPanel.preflight）', () => {
    const baseParams = {
      whisper_model_size: 'medium',
      vocal_separation: false,
      align: false,
      llm_remote: false,
      llm_model_family: 'gemma4',
      llm_model_size: '9b',
      vlm_remote: false,
    }

    it('最小案（無 vocal_separation/align/vlm）→ 只有 whisper + llm 兩道', () => {
      expect(META.modelRequirements!(baseParams)).toEqual([
        { slot: 'whisper', variant: 'medium', categories: ['stt'] },
        { slot: 'llm', family: 'gemma4', size: '9b' },
      ])
    })

    it('vocal_separation=true → 插入 demucs guard（whisper 之後、align 之前）', () => {
      const reqs = META.modelRequirements!({ ...baseParams, vocal_separation: true })
      expect(reqs).toEqual([
        { slot: 'whisper', variant: 'medium', categories: ['stt'] },
        { slot: 'separate', variant: 'htdemucs_6s', family: 'demucs', categories: ['separate'] },
        { slot: 'llm', family: 'gemma4', size: '9b' },
      ])
    })

    it('align=true → 插入 categories-only align guard', () => {
      const reqs = META.modelRequirements!({ ...baseParams, align: true })
      expect(reqs).toEqual([
        { slot: 'whisper', variant: 'medium', categories: ['stt'] },
        { slot: 'align', categories: ['alignment'] },
        { slot: 'llm', family: 'gemma4', size: '9b' },
      ])
    })

    it('llm_remote=true → LLM guard 跳過（雲端不需下載）', () => {
      const reqs = META.modelRequirements!({ ...baseParams, llm_remote: true })
      expect(reqs).toEqual([{ slot: 'whisper', variant: 'medium', categories: ['stt'] }])
    })

    it('vlm 有 local 值（vlm_model_family）且非 remote → 追加 vlm guard（順序在最後）', () => {
      const reqs = META.modelRequirements!({ ...baseParams, vlm_model_family: 'qwen3vl', vlm_model_size: '8b' })
      expect(reqs).toEqual([
        { slot: 'whisper', variant: 'medium', categories: ['stt'] },
        { slot: 'llm', family: 'gemma4', size: '9b' },
        { slot: 'vlm', family: 'qwen3vl', size: '8b' },
      ])
    })

    it('vlm 有 remote 值（vlm_remote_model）但 vlm_remote=true → 不追加 vlm guard', () => {
      const reqs = META.modelRequirements!({ ...baseParams, vlm_remote: true, vlm_remote_model: 'gpt-4o' })
      expect(reqs).toEqual([
        { slot: 'whisper', variant: 'medium', categories: ['stt'] },
        { slot: 'llm', family: 'gemma4', size: '9b' },
      ])
    })

    it('vlm 全空（無 family 無 remote_model）→ 不追加 vlm guard（VLM 選配、可留空）', () => {
      const reqs = META.modelRequirements!(baseParams)
      expect(reqs.find((r) => r.slot === 'vlm')).toBeUndefined()
    })

    it('全五道齊開（vocal_separation+align+local llm+local vlm）→ 順序 whisper→separate→align→llm→vlm', () => {
      const reqs = META.modelRequirements!({
        ...baseParams,
        vocal_separation: true,
        align: true,
        vlm_model_family: 'qwen3vl',
        vlm_model_size: '8b',
      })
      expect(reqs.map((r) => r.slot)).toEqual(['whisper', 'separate', 'align', 'llm', 'vlm'])
    })
  })

  describe('encodeModelToken / decodeModelToken（llm/vlm 共用，無 quantization）', () => {
    it('local：encode "family:size"', () => {
      expect(encodeModelToken({ llm_model_family: 'gemma4', llm_model_size: '9b' }, 'llm')).toBe('gemma4:9b')
    })

    it('local 全空 → encode 空字串（VLM「不使用」哨兵值對齊）', () => {
      expect(encodeModelToken({}, 'vlm')).toBe('')
    })

    it('remote：encode "remote:provider:connId:modelId"', () => {
      expect(encodeModelToken(
        { llm_remote: true, llm_provider: 'openai', llm_conn_id: 1, llm_remote_model: 'gpt-4o' },
        'llm',
      )).toBe('remote:openai:1:gpt-4o')
    })

    it('decode local token → 六欄正確展開，remote 側清空', () => {
      expect(decodeModelToken('gemma4:9b', 'llm')).toEqual({
        llm_remote: false,
        llm_provider: undefined,
        llm_conn_id: undefined,
        llm_remote_model: undefined,
        llm_model_family: 'gemma4',
        llm_model_size: '9b',
      })
    })

    it('decode remote token → 六欄正確展開，local 側清空', () => {
      expect(decodeModelToken('remote:ollama:3:llama3:8b', 'vlm')).toEqual({
        vlm_remote: true,
        vlm_provider: 'ollama',
        vlm_conn_id: 3,
        vlm_remote_model: 'llama3:8b', // modelId 含冒號時原樣保留
        vlm_model_family: undefined,
        vlm_model_size: undefined,
      })
    })

    it('decode 空字串 token → 六欄全清、remote=false（VLM 清空語意）', () => {
      expect(decodeModelToken('', 'vlm')).toEqual({
        vlm_remote: false,
        vlm_provider: undefined,
        vlm_conn_id: undefined,
        vlm_remote_model: undefined,
        vlm_model_family: undefined,
        vlm_model_size: undefined,
      })
    })

    it('roundtrip：encode(decode(token)) === token（local/remote 各一）', () => {
      for (const [token, prefix] of [['gemma4:9b', 'llm'], ['remote:openai:1:gpt-4o', 'vlm']] as const) {
        const patch = decodeModelToken(token, prefix)
        expect(encodeModelToken(patch, prefix)).toBe(token)
      }
    })
  })
})
