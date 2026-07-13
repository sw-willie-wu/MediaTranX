/**
 * image.crop META 單測（統一參數元件 spec §4；批 4 Task 4.3）。
 * 覆蓋 defaults/validate/seedOnFileChange 三個 hook，仿 video/__tests__/crop.meta.test.ts。
 * schema 準繩＝後端 ImageCropRequest（backend/app/api/routes/image/crop.py）：
 * x/y default 0、width/height 必填（gt=0，UI min=1——PIL 無取偶約束，異於 video 版 min=2）。
 */
import { describe, it, expect } from 'vitest'
import { META } from '../crop.meta'

describe('image.crop META', () => {
  it('defaults() 只含有 default 的欄位（x/y=0，width/height 無 default）', () => {
    expect(META.defaults()).toEqual({ x: 0, y: 0 })
  })

  describe('validate', () => {
    it('width/height 皆未定義 → size_error', () => {
      expect(META.validate!({})).toBe('image.crop.size_error')
    })

    it('width 未定義、height 已定義 → size_error', () => {
      expect(META.validate!({ height: 100 })).toBe('image.crop.size_error')
    })

    it('width<=0 → size_error', () => {
      expect(META.validate!({ width: 0, height: 100 })).toBe('image.crop.size_error')
    })

    it('height<=0 → size_error', () => {
      expect(META.validate!({ width: 100, height: -1 })).toBe('image.crop.size_error')
    })

    it('width/height 非有限數（NaN）→ size_error', () => {
      expect(META.validate!({ width: NaN, height: 100 })).toBe('image.crop.size_error')
    })

    it('width/height 皆為正數 → null（合法，含 1px 邊界——PIL 無取偶約束）', () => {
      expect(META.validate!({ x: 0, y: 0, width: 1, height: 1 })).toBeNull()
      expect(META.validate!({ x: 0, y: 0, width: 640, height: 480 })).toBeNull()
    })
  })

  describe('seedOnFileChange', () => {
    it('換檔無條件重置 x/y=0、width/height=undefined', () => {
      expect(
        META.seedOnFileChange!({ width: 1920, height: 1080 }, { x: 10, y: 20, width: 300, height: 200 }),
      ).toEqual({ x: 0, y: 0, width: undefined, height: undefined })
    })

    it('fileInfo 為 null 仍重置（不依賴 fileInfo 內容）', () => {
      expect(META.seedOnFileChange!(null, { x: 10, y: 20, width: 300, height: 200 })).toEqual({
        x: 0,
        y: 0,
        width: undefined,
        height: undefined,
      })
    })
  })

  it('schema 不變量：每個 enum 欄位 default ∈ options（本 tool 無 enum 欄位，vacuously 過）', () => {
    for (const f of META.schema) {
      if (f.type === 'enum' && f.default !== undefined) {
        expect(f.options ?? []).toContain(f.default)
      }
    }
  })

  it('schema 欄位集合＝x/y/width/height（不含 file_id/suppress_results）', () => {
    expect(META.schema.map((f) => f.name)).toEqual(['x', 'y', 'width', 'height'])
  })

  it('width/height min=1（異於 video.crop 的 min=2——PIL 裁切無 ffmpeg 向下取偶約束）', () => {
    const width = META.schema.find((f) => f.name === 'width')!
    const height = META.schema.find((f) => f.name === 'height')!
    expect(width.min).toBe(1)
    expect(height.min).toBe(1)
  })

  it('multiSelect=false（舊 ImageView 無 crop 批次 case，退回 single）', () => {
    expect(META.multiSelect).toBe(false)
  })
})
