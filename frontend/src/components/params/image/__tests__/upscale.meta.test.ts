/**
 * image.upscale META 單測（統一參數元件 spec §4；批 4 Task 4.4）。
 * 覆蓋 defaults/buildSubmit（face_fix gate）/modelRequirements（id 型、face_fix 條件追加）。
 */
import { describe, it, expect } from 'vitest'
import { META } from '../upscale.meta'

describe('image.upscale META', () => {
  it('defaults() 含 model_id/scale/sharpen/face_fix/face_restore_upscale（face_restore_model_id 無 default，不出現）', () => {
    expect(META.defaults()).toEqual({
      model_id: 'realesrgan-x4plus',
      scale: 4,
      sharpen: false,
      face_fix: false,
      face_restore_upscale: 2,
    })
  })

  it('schema 不變量：每個 enum 欄位 default ∈ options', () => {
    for (const f of META.schema) {
      if (f.type === 'enum' && f.default !== undefined) {
        expect(f.options ?? [], f.name).toContain(f.default)
      }
    }
  })

  it('agentExecuteLabel 沿舊 ImageUpscalePanel.agentSchema.execute.label（與 labelKey 不同）', () => {
    expect(META.agentExecuteLabel).toBe('panel.upscale.execute')
    expect(META.agentExecuteLabel).not.toBe(META.labelKey)
  })

  it('multiSelect true（舊 ImageView.handleMultiExecute 已支援批次）', () => {
    expect(META.multiSelect).toBe(true)
  })

  it('persistedModelFields = [model_id, face_restore_model_id]', () => {
    expect(META.persistedModelFields).toEqual(['model_id', 'face_restore_model_id'])
  })

  describe('buildSubmit — face_fix gate（鏡射舊 getParams 三元式）', () => {
    it('face_fix=false → face_restore_model_id 明確送 null（即使殘留舊選值）', () => {
      const spec = META.buildSubmit!({
        model_id: 'realesrgan-x4plus', scale: 4, sharpen: false,
        face_fix: false, face_restore_model_id: 'gfpgan-v1.4', face_restore_upscale: 2,
      })
      expect(spec.payload.face_restore_model_id).toBeNull()
    })

    it('face_fix=true 但未選 face 模型（undefined）→ 送 null', () => {
      const spec = META.buildSubmit!({
        model_id: 'realesrgan-x4plus', scale: 4, sharpen: false,
        face_fix: true, face_restore_upscale: 2,
      })
      expect(spec.payload.face_restore_model_id).toBeNull()
    })

    it('face_fix=true 且已選 face 模型 → 原樣送出', () => {
      const spec = META.buildSubmit!({
        model_id: 'realesrgan-x4plus', scale: 4, sharpen: false,
        face_fix: true, face_restore_model_id: 'gfpgan-v1.4', face_restore_upscale: 2,
      })
      expect(spec.payload.face_restore_model_id).toBe('gfpgan-v1.4')
    })

    it('apiPath/taskType/labelKey 沿 META', () => {
      const spec = META.buildSubmit!(META.defaults())
      expect(spec.apiPath).toBe('/image/upscale')
      expect(spec.taskType).toBe('image.upscale')
      expect(spec.labelKey).toBe('image.upscale.task_label')
    })
  })

  describe('modelRequirements — id 型（跨家族），face_fix 條件追加第二道', () => {
    it('face_fix=false → 僅一道需求（主模型，slot=upscale, id=model_id）', () => {
      expect(META.modelRequirements!({ model_id: 'realesrgan-x4plus', face_fix: false })).toEqual([
        { slot: 'upscale', id: 'realesrgan-x4plus' },
      ])
    })

    it('face_fix=true 且已選 face 模型 → 兩道需求', () => {
      expect(META.modelRequirements!({
        model_id: 'swinir-lightweight-x4', face_fix: true, face_restore_model_id: 'gfpgan-v1.4',
      })).toEqual([
        { slot: 'upscale', id: 'swinir-lightweight-x4' },
        { slot: 'upscale', id: 'gfpgan-v1.4' },
      ])
    })

    it('face_fix=true 但未選 face 模型 → 仍僅一道需求（不追加空 id）', () => {
      expect(META.modelRequirements!({ model_id: 'realesrgan-x4plus', face_fix: true })).toEqual([
        { slot: 'upscale', id: 'realesrgan-x4plus' },
      ])
    })

    it('model_id 未定義時為空字串（不 throw）', () => {
      expect(META.modelRequirements!({})).toEqual([{ slot: 'upscale', id: '' }])
    })
  })

  it('無 modelRequirement（單數）——本工具走複數 modelRequirements', () => {
    expect(META.modelRequirement).toBeUndefined()
  })
})
