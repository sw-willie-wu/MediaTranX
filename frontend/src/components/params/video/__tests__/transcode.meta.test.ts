/**
 * transcode.meta.ts 單測（統一參數元件 spec §4；批 1 Task 1.1）。
 * 覆蓋 defaults/validate/buildSubmit 三個 hook＋ schema 不變量。
 */
import { describe, it, expect } from 'vitest'
import { META, AUDIO_FORMATS } from '../transcode.meta'

describe('video.transcode META', () => {
  it('defaults() 只含有 default 的欄位', () => {
    expect(META.defaults()).toEqual({
      output_format: 'mp4',
      video_codec: 'h264',
      crf: 23,
      audio_codec: 'aac',
      preset: 'medium',
      resolution: '',
      scale_algorithm: 'bicubic',
    })
  })

  it('schema 不變量：每個 enum 欄位 default ∈ options', () => {
    for (const f of META.schema) {
      if (f.type === 'enum' && f.default !== undefined) {
        expect(f.options ?? [], f.name).toContain(f.default)
      }
    }
  })

  it('AUDIO_FORMATS 涵蓋工具頁分流四格式', () => {
    expect([...AUDIO_FORMATS].sort()).toEqual(['aac', 'flac', 'mp3', 'wav'])
  })

  describe('validate（resolution 寬鬆格式檢查）', () => {
    it('空字串 → null（保持原始）', () => {
      expect(META.validate!({ resolution: '' })).toBeNull()
    })

    it('未定義 → null', () => {
      expect(META.validate!({})).toBeNull()
    })

    it('"1920x1080" → null', () => {
      expect(META.validate!({ resolution: '1920x1080' })).toBeNull()
    })

    it('"abc" → resolution_error', () => {
      expect(META.validate!({ resolution: 'abc' })).toBe('video.transcode.resolution_error')
    })

    it('"1920x" → resolution_error（不完整）', () => {
      expect(META.validate!({ resolution: '1920x' })).toBe('video.transcode.resolution_error')
    })
  })

  describe('buildSubmit', () => {
    it('mp3 → 分流 extract-audio，含 audio_bitrate', () => {
      const spec = META.buildSubmit!({ output_format: 'mp3', audio_bitrate: '192k' })
      expect(spec).toEqual({
        apiPath: '/video/extract-audio',
        payload: { audio_format: 'mp3', audio_bitrate: '192k' },
        taskType: 'video.extract_audio',
        labelKey: 'video.transcode.extract_audio',
      })
    })

    it('mp3 → 分流 extract-audio，無 audio_bitrate（未設定）', () => {
      const spec = META.buildSubmit!({ output_format: 'mp3' })
      expect(spec.payload).toEqual({ audio_format: 'mp3' })
    })

    it('wav → 分流 extract-audio，即使帶 audio_bitrate 也不送（無損格式）', () => {
      const spec = META.buildSubmit!({ output_format: 'wav', audio_bitrate: '320k' })
      expect(spec.payload).toEqual({ audio_format: 'wav' })
    })

    it('flac → 分流 extract-audio，不送 audio_bitrate', () => {
      const spec = META.buildSubmit!({ output_format: 'flac', audio_bitrate: '320k' })
      expect(spec.payload).toEqual({ audio_format: 'flac' })
    })

    it('mp4 → /video/transcode 原樣形狀（含 audio_bitrate 若有設定，後端真的收此欄）', () => {
      const params = { output_format: 'mp4', video_codec: 'h264', crf: 23, audio_codec: 'aac' }
      const spec = META.buildSubmit!(params)
      expect(spec).toEqual({
        apiPath: '/video/transcode',
        payload: { output_format: 'mp4', video_codec: 'h264', crf: 23, audio_codec: 'aac' },
        taskType: 'video.transcode',
        labelKey: 'video.transcode.task_label',
      })
    })

    it('gif → /video/transcode 原樣形狀（動圖路徑）', () => {
      const params = { output_format: 'gif', fps: 12 }
      const spec = META.buildSubmit!(params)
      expect(spec.apiPath).toBe('/video/transcode')
      expect(spec.payload).toEqual({ output_format: 'gif', fps: 12 })
    })

    it('payload 一律不含 file_id', () => {
      for (const fmt of ['mp3', 'mp4', 'gif']) {
        const spec = META.buildSubmit!({ output_format: fmt })
        expect(spec.payload).not.toHaveProperty('file_id')
      }
    })
  })

  describe('visibleWhen 欄位可見性', () => {
    const field = (name: string) => META.schema.find(f => f.name === name)!

    it('video_codec：一般視訊可見，音訊/動圖不可見', () => {
      const f = field('video_codec')
      expect(f.visibleWhen!({ output_format: 'mp4' })).toBe(true)
      expect(f.visibleWhen!({ output_format: 'mp3' })).toBe(false)
      expect(f.visibleWhen!({ output_format: 'gif' })).toBe(false)
    })

    it('audio_codec：動圖不可見，其餘可見', () => {
      const f = field('audio_codec')
      expect(f.visibleWhen!({ output_format: 'mp4' })).toBe(true)
      expect(f.visibleWhen!({ output_format: 'mp3' })).toBe(true)
      expect(f.visibleWhen!({ output_format: 'gif' })).toBe(false)
    })

    it('fps：僅動圖可見', () => {
      const f = field('fps')
      expect(f.visibleWhen!({ output_format: 'gif' })).toBe(true)
      expect(f.visibleWhen!({ output_format: 'apng' })).toBe(true)
      expect(f.visibleWhen!({ output_format: 'mp4' })).toBe(false)
    })

    it('audio_bitrate：僅純音訊且非無損格式可見', () => {
      const f = field('audio_bitrate')
      expect(f.visibleWhen!({ output_format: 'mp3' })).toBe(true)
      expect(f.visibleWhen!({ output_format: 'aac' })).toBe(true)
      expect(f.visibleWhen!({ output_format: 'wav' })).toBe(false)
      expect(f.visibleWhen!({ output_format: 'flac' })).toBe(false)
      expect(f.visibleWhen!({ output_format: 'mp4' })).toBe(false)
    })

    it('scale_algorithm：非音訊且已填 resolution 才可見', () => {
      const f = field('scale_algorithm')
      expect(f.visibleWhen!({ output_format: 'mp4', resolution: '1920x1080' })).toBe(true)
      expect(f.visibleWhen!({ output_format: 'mp4', resolution: '' })).toBe(false)
      expect(f.visibleWhen!({ output_format: 'mp3', resolution: '1920x1080' })).toBe(false)
    })

    it('crf：與 video_codec 同閘門', () => {
      const f = field('crf')
      expect(f.visibleWhen!({ output_format: 'mp4' })).toBe(true)
      expect(f.visibleWhen!({ output_format: 'gif' })).toBe(false)
      expect(f.visibleWhen!({ output_format: 'mp3' })).toBe(false)
    })
  })
})
