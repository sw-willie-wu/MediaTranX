/**
 * extract_audio.meta.ts 單測（統一參數元件 spec §4；批 1 Task 1.1）。
 * pipeline 節點用 META——無 buildSubmit/validate,只驗 defaults/schema 不變量/visibleWhen。
 */
import { describe, it, expect } from 'vitest'
import { META } from '../extract_audio.meta'

describe('video.extract_audio META', () => {
  it('toolKey/apiPath/taskType/labelKey 對應後端 /video/extract-audio', () => {
    expect(META.toolKey).toBe('video.extract_audio')
    expect(META.apiPath).toBe('/video/extract-audio')
    expect(META.taskType).toBe('video.extract_audio')
    expect(META.labelKey).toBe('video.transcode.extract_audio')
  })

  it('defaults() 只含有 default 的欄位', () => {
    expect(META.defaults()).toEqual({ audio_format: 'mp3' })
  })

  it('schema 不變量：每個 enum 欄位 default ∈ options', () => {
    for (const f of META.schema) {
      if (f.type === 'enum' && f.default !== undefined) {
        expect(f.options ?? [], f.name).toContain(f.default)
      }
    }
  })

  it('無 buildSubmit（pipeline 節點直傳）', () => {
    expect(META.buildSubmit).toBeUndefined()
  })

  it('multiSelect true', () => {
    expect(META.multiSelect).toBe(true)
  })

  describe('audio_bitrate visibleWhen：無損格式（wav/flac）不可見', () => {
    const field = META.schema.find(f => f.name === 'audio_bitrate')!

    it('mp3/aac → 可見', () => {
      expect(field.visibleWhen!({ audio_format: 'mp3' })).toBe(true)
      expect(field.visibleWhen!({ audio_format: 'aac' })).toBe(true)
    })

    it('wav/flac → 不可見', () => {
      expect(field.visibleWhen!({ audio_format: 'wav' })).toBe(false)
      expect(field.visibleWhen!({ audio_format: 'flac' })).toBe(false)
    })
  })
})
