/**
 * video.crop META 單測（統一參數元件 spec §4；批 2 Task 2.1）。
 * 覆蓋 defaults/validate/seedOnFileChange 三個 hook。
 * schema 準繩＝後端 VideoCropRequest（backend/app/api/routes/video/crop.py）：
 * x/y default 0（ge=0）、width/height 必填（gt=0，UI 收斂 min=2 向下取偶）。
 */
import { describe, it, expect } from 'vitest'
import { META } from '../crop.meta'

describe('video.crop META', () => {
  it('defaults() 只含有 default 的欄位（x/y=0，width/height 無 default）', () => {
    expect(META.defaults()).toEqual({ x: 0, y: 0 })
  })

  describe('validate', () => {
    it('width/height 皆未定義 → size_error', () => {
      expect(META.validate!({})).toBe('video.crop.size_error')
    })

    it('width 未定義、height 已定義 → size_error', () => {
      expect(META.validate!({ height: 100 })).toBe('video.crop.size_error')
    })

    it('width<=0 → size_error', () => {
      expect(META.validate!({ width: 0, height: 100 })).toBe('video.crop.size_error')
    })

    it('height<=0 → size_error', () => {
      expect(META.validate!({ width: 100, height: -1 })).toBe('video.crop.size_error')
    })

    it('width/height 非有限數（NaN）→ size_error', () => {
      expect(META.validate!({ width: NaN, height: 100 })).toBe('video.crop.size_error')
    })

    it('width/height 皆為正數 → null（合法）', () => {
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

  it('width/height min=2（UI 收斂：後端向下取偶，1 會取到 0 直接 ValueError）', () => {
    const width = META.schema.find((f) => f.name === 'width')!
    const height = META.schema.find((f) => f.name === 'height')!
    expect(width.min).toBe(2)
    expect(height.min).toBe(2)
  })
})
