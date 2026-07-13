/**
 * video.enhance META 單測（統一參數元件 spec §4；批 2 Task 2.3）。
 * 覆蓋 defaults/modelRequirement 兩個 hook＋ schema 不變量。
 */
import { describe, it, expect } from 'vitest'
import { META } from '../enhance.meta'

describe('video.enhance META', () => {
  it('defaults() 含 model/variant/output_format/video_codec（全欄皆有 default）', () => {
    expect(META.defaults()).toEqual({
      model: 'realesrgan',
      variant: 'x4plus',
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

  it('agentExecuteLabel 沿舊 VideoEnhancePanel.agentSchema.execute.label（與 labelKey 不同）', () => {
    expect(META.agentExecuteLabel).toBe('panel.enhance.execute')
    expect(META.agentExecuteLabel).not.toBe(META.labelKey)
  })

  it('multiSelect true（舊 VideoView.handleMultiExecute 已支援批次）', () => {
    expect(META.multiSelect).toBe(true)
  })

  it('persistedModelFields = [variant]', () => {
    expect(META.persistedModelFields).toEqual(['variant'])
  })

  describe('modelRequirement', () => {
    it('回 variant 型需求（slot=enhance，variant=params.variant，family=realesrgan，categories=[upscale,video_enhance]）', () => {
      expect(META.modelRequirement!({ variant: 'x4plus' })).toEqual({
        slot: 'enhance',
        variant: 'x4plus',
        family: 'realesrgan',
        categories: ['upscale', 'video_enhance'],
      })
    })

    it('variant 未定義時為空字串（不 throw）', () => {
      expect(META.modelRequirement!({})).toEqual({
        slot: 'enhance',
        variant: '',
        family: 'realesrgan',
        categories: ['upscale', 'video_enhance'],
      })
    })
  })

  it('無 buildSubmit（沿舊 getParams 原樣透傳，無分流需求）', () => {
    expect(META.buildSubmit).toBeUndefined()
  })
})
