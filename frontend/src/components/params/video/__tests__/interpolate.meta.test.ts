/**
 * video.interpolate META 單測（統一參數元件 spec §4；批 2 Task 2.3）。
 * 覆蓋 defaults/buildSubmit/modelRequirement 三個 hook＋ schema 不變量。
 */
import { describe, it, expect } from 'vitest'
import { META } from '../interpolate.meta'

describe('video.interpolate META', () => {
  it('defaults() 含 model/mode/target_fps/output_format/video_codec（全欄皆有 default）', () => {
    expect(META.defaults()).toEqual({
      model: 'v4.26',
      mode: '2x',
      target_fps: 60,
      output_format: 'mp4',
      video_codec: 'h264',
    })
  })

  it('schema 不變量：每個 enum 欄位 default ∈ options', () => {
    for (const f of META.schema) {
      if (f.type === 'enum' && f.default !== undefined) {
        expect(f.options ?? [], f.name).toContain(f.default)
      }
    }
  })

  it('agentExecuteLabel 沿舊 VideoInterpolatePanel.agentSchema.execute.label（與 labelKey 不同）', () => {
    expect(META.agentExecuteLabel).toBe('panel.interpolate.execute')
    expect(META.agentExecuteLabel).not.toBe(META.labelKey)
  })

  it('multiSelect true（舊 VideoView.handleMultiExecute 已支援批次）', () => {
    expect(META.multiSelect).toBe(true)
  })

  it('persistedModelFields = [model]', () => {
    expect(META.persistedModelFields).toEqual(['model'])
  })

  describe('modelRequirement', () => {
    it('回 variant 型需求（slot=interpolate，variant=params.model，categories=[interpolate]）', () => {
      expect(META.modelRequirement!({ model: 'v4.26' })).toEqual({
        slot: 'interpolate',
        variant: 'v4.26',
        categories: ['interpolate'],
      })
    })

    it('model 未定義時 variant 為空字串（不 throw）', () => {
      expect(META.modelRequirement!({})).toEqual({
        slot: 'interpolate',
        variant: '',
        categories: ['interpolate'],
      })
    })
  })

  describe('buildSubmit', () => {
    it('mode=custom → payload 保留 target_fps', () => {
      const spec = META.buildSubmit!({ model: 'v4.26', mode: 'custom', target_fps: 90, output_format: 'mp4', video_codec: 'h264' })
      expect(spec).toEqual({
        apiPath: '/video/interpolate',
        payload: { model: 'v4.26', mode: 'custom', target_fps: 90, output_format: 'mp4', video_codec: 'h264' },
        taskType: 'video.interpolate',
        labelKey: 'video.interpolate.task_label',
      })
    })

    it('mode=2x → payload 剔除 target_fps（鏡射舊 getParams 的 undefined 語意）', () => {
      const spec = META.buildSubmit!({ model: 'v4.26', mode: '2x', target_fps: 60, output_format: 'mp4', video_codec: 'h264' })
      expect(spec.payload).not.toHaveProperty('target_fps')
      expect(spec.payload).toEqual({ model: 'v4.26', mode: '2x', output_format: 'mp4', video_codec: 'h264' })
    })

    it('mode=4x → payload 剔除 target_fps', () => {
      const spec = META.buildSubmit!({ model: 'v4.26', mode: '4x', target_fps: 60, output_format: 'mp4', video_codec: 'h264' })
      expect(spec.payload).not.toHaveProperty('target_fps')
    })

    it('payload 一律不含 file_id', () => {
      for (const mode of ['2x', '4x', 'custom']) {
        const spec = META.buildSubmit!({ model: 'v4.26', mode, target_fps: 60 })
        expect(spec.payload).not.toHaveProperty('file_id')
      }
    })
  })

  describe('target_fps 可見性', () => {
    const field = () => META.schema.find((f) => f.name === 'target_fps')!

    it('mode=custom → 可見', () => {
      expect(field().visibleWhen!({ mode: 'custom' })).toBe(true)
    })

    it('mode=2x/4x → 不可見', () => {
      expect(field().visibleWhen!({ mode: '2x' })).toBe(false)
      expect(field().visibleWhen!({ mode: '4x' })).toBe(false)
    })
  })
})
