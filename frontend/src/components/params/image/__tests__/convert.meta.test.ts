/**
 * image.convert META 單測（統一參數元件 spec §4；批 4 Task 4.1）。
 * 覆蓋 defaults()／schema 不變量／buildSubmit 的 width/height/scale 三態互斥清理。
 */
import { describe, it, expect } from 'vitest'
import { META } from '../convert.meta'

describe('image.convert META', () => {
  it('defaults() 只含有 default 的欄位', () => {
    expect(META.defaults()).toEqual({
      output_format: 'png',
      quality: 85,
      coalesce: false,
    })
  })

  it('schema 欄位集合＝後端全集 6 欄', () => {
    expect(META.schema.map((f) => f.name)).toEqual([
      'output_format', 'quality', 'width', 'height', 'scale', 'coalesce',
    ])
  })

  it('quality visibleWhen 僅 jpg/webp', () => {
    const f = META.schema.find((x) => x.name === 'quality')!
    expect(f.visibleWhen!({ output_format: 'jpg' })).toBe(true)
    expect(f.visibleWhen!({ output_format: 'webp' })).toBe(true)
    expect(f.visibleWhen!({ output_format: 'png' })).toBe(false)
    expect(f.visibleWhen!({ output_format: 'gif' })).toBe(false)
  })

  it('coalesce visibleWhen 僅 gif', () => {
    const f = META.schema.find((x) => x.name === 'coalesce')!
    expect(f.visibleWhen!({ output_format: 'gif' })).toBe(true)
    expect(f.visibleWhen!({ output_format: 'png' })).toBe(false)
  })

  it('schema 不變量：enum 欄位 default ∈ options（output_format）', () => {
    for (const f of META.schema) {
      if (f.type === 'enum' && f.default !== undefined) {
        expect(f.options ?? []).toContain(f.default)
      }
    }
  })

  describe('buildSubmit — width/height/scale 三態互斥清理', () => {
    it('scale 有值 → width/height 被剔除，scale 保留', () => {
      const spec = META.buildSubmit!({ output_format: 'png', scale: 1.5, width: 800, height: 600 })
      expect(spec.payload).toEqual({ output_format: 'png', scale: 1.5 })
    })

    it('width/height 有值、scale 未定義 → 兩者保留', () => {
      const spec = META.buildSubmit!({ output_format: 'png', width: 800, height: 600 })
      expect(spec.payload).toEqual({ output_format: 'png', width: 800, height: 600 })
    })

    it('只有 width、無 height/scale → width 保留，無 scale key', () => {
      const spec = META.buildSubmit!({ output_format: 'png', width: 800 })
      expect(spec.payload).toEqual({ output_format: 'png', width: 800 })
      expect('scale' in spec.payload).toBe(false)
    })

    it('三者皆未定義（original 模式）→ payload 不含三欄任一 key', () => {
      const spec = META.buildSubmit!({ output_format: 'png' })
      expect('scale' in spec.payload).toBe(false)
      expect('width' in spec.payload).toBe(false)
      expect('height' in spec.payload).toBe(false)
    })

    it('scale=NaN（非有限數）視為未設 → 走 width/height 分支', () => {
      const spec = META.buildSubmit!({ output_format: 'png', scale: NaN, width: 800 })
      expect(spec.payload).toEqual({ output_format: 'png', width: 800 })
    })

    it('apiPath/taskType/labelKey 與 meta 一致', () => {
      const spec = META.buildSubmit!({ output_format: 'png' })
      expect(spec.apiPath).toBe('/image/convert')
      expect(spec.taskType).toBe('image.convert')
      expect(spec.labelKey).toBe('image.convert.task_label')
    })
  })

  it('downloadFormatField="output_format"；multiSelect=true；agentExecuteLabel="panel.transcode.execute"', () => {
    expect(META.downloadFormatField).toBe('output_format')
    expect(META.multiSelect).toBe(true)
    expect(META.agentExecuteLabel).toBe('panel.transcode.execute')
  })

  it('無 validate/modelRequirement/seedOnFileChange', () => {
    expect(META.validate).toBeUndefined()
    expect(META.modelRequirement).toBeUndefined()
    expect(META.modelRequirements).toBeUndefined()
    expect(META.seedOnFileChange).toBeUndefined()
  })
})
