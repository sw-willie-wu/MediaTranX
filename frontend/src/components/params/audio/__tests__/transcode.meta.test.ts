/**
 * audio.transcode META 單測（統一參數元件 spec §4；批 3 Task 3.1）。
 * 覆蓋 defaults/buildSubmit（剔欄/歸零/wma 全集）＋ schema 不變量。
 */
import { describe, it, expect } from 'vitest'
import { META, LOSSLESS_FORMATS } from '../transcode.meta'

describe('audio.transcode META', () => {
  it('defaults() 只含有 default 的欄位', () => {
    expect(META.defaults()).toEqual({
      output_format: 'mp3',
      audio_bitrate: '192k',
    })
  })

  it('schema 不變量：每個 enum 欄位 default ∈ options', () => {
    for (const f of META.schema) {
      if (f.type === 'enum' && f.default !== undefined) {
        expect(f.options ?? [], f.name).toContain(f.default)
      }
    }
  })

  it('output_format schema 含 wma（後端 _FORMAT_CODEC_MAP 全集，UI 過濾另見 Params 單測）', () => {
    const f = META.schema.find((x) => x.name === 'output_format')!
    expect(f.options).toContain('wma')
  })

  it('LOSSLESS_FORMATS 沿舊 panel 常量', () => {
    expect([...LOSSLESS_FORMATS].sort()).toEqual(['aiff', 'alac', 'flac', 'wav'])
  })

  it('agentRequiresConfirm 未設（host 預設 true）；agentExecuteLabel 設為舊 panel 字串', () => {
    expect(META.agentRequiresConfirm).toBeUndefined()
    expect(META.agentExecuteLabel).toBe('panel.audio_transcode.execute')
  })

  describe('buildSubmit', () => {
    it('mp3 + audio_bitrate → 原樣帶入', () => {
      const spec = META.buildSubmit!({ output_format: 'mp3', audio_bitrate: '256k', sample_rate: undefined })
      expect(spec).toEqual({
        apiPath: '/audio/transcode',
        payload: { output_format: 'mp3', audio_bitrate: '256k', sample_rate: null },
        taskType: 'audio.transcode',
        labelKey: 'audio.transcode.task_label',
      })
    })

    it('audio_bitrate 空字串（keep_original 選項）→ 剔除該欄', () => {
      const spec = META.buildSubmit!({ output_format: 'mp3', audio_bitrate: '' })
      expect(spec.payload).toEqual({ output_format: 'mp3', sample_rate: null })
    })

    it('audio_bitrate 未設 → 剔除該欄', () => {
      const spec = META.buildSubmit!({ output_format: 'mp3' })
      expect(spec.payload).toEqual({ output_format: 'mp3', sample_rate: null })
    })

    it('無損格式（wav）→ 即使帶 audio_bitrate 也剔除', () => {
      const spec = META.buildSubmit!({ output_format: 'wav', audio_bitrate: '320k' })
      expect(spec.payload).toEqual({ output_format: 'wav', sample_rate: null })
    })

    it('無損格式（flac/alac/aiff）→ 同樣剔除 audio_bitrate', () => {
      for (const fmt of ['flac', 'alac', 'aiff']) {
        const spec = META.buildSubmit!({ output_format: fmt, audio_bitrate: '320k' })
        expect(spec.payload).toEqual({ output_format: fmt, sample_rate: null })
      }
    })

    it('sample_rate 為 number → 原樣送出', () => {
      const spec = META.buildSubmit!({ output_format: 'mp3', sample_rate: 44100 })
      expect(spec.payload.sample_rate).toBe(44100)
    })

    it('sample_rate 空/未設 → 送 null（核對舊 panel 行為，非省略）', () => {
      expect(META.buildSubmit!({ output_format: 'mp3' }).payload.sample_rate).toBeNull()
      expect(META.buildSubmit!({ output_format: 'mp3', sample_rate: undefined }).payload.sample_rate).toBeNull()
      expect(META.buildSubmit!({ output_format: 'mp3', sample_rate: '' }).payload.sample_rate).toBeNull()
    })

    it('channels 為 number → 帶入 payload；未設 → 不含此鍵（新欄位、無舊行為需鏡射）', () => {
      const withChannels = META.buildSubmit!({ output_format: 'mp3', channels: 2 })
      expect(withChannels.payload.channels).toBe(2)

      const withoutChannels = META.buildSubmit!({ output_format: 'mp3' })
      expect(withoutChannels.payload).not.toHaveProperty('channels')
    })

    it('payload 一律不含 file_id', () => {
      for (const fmt of ['mp3', 'wav', 'wma']) {
        const spec = META.buildSubmit!({ output_format: fmt })
        expect(spec.payload).not.toHaveProperty('file_id')
      }
    })
  })

  describe('visibleWhen', () => {
    it('audio_bitrate：無損格式不可見，其餘可見', () => {
      const f = META.schema.find((x) => x.name === 'audio_bitrate')!
      expect(f.visibleWhen!({ output_format: 'mp3' })).toBe(true)
      expect(f.visibleWhen!({ output_format: 'wma' })).toBe(true)
      expect(f.visibleWhen!({ output_format: 'wav' })).toBe(false)
      expect(f.visibleWhen!({ output_format: 'flac' })).toBe(false)
      expect(f.visibleWhen!({ output_format: 'alac' })).toBe(false)
      expect(f.visibleWhen!({ output_format: 'aiff' })).toBe(false)
    })
  })
})
