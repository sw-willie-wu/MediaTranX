/**
 * cut.meta.ts 單測（統一參數元件 spec §4；Task 0.3）。
 * 覆蓋 defaults/validate/seedOnFileChange 三個 hook＋時間字串 helper。
 */
import { describe, it, expect } from 'vitest'
import { META, parseTimeToSeconds, secondsToTime } from '../cut.meta'

describe('video.cut META', () => {
  it('defaults() 只含有 default 的欄位（start_time=0 讓 pipeline 節點不缺鍵送 422；end_time 必填無 default）', () => {
    expect(META.defaults()).toEqual({ start_time: 0, stream_copy: true })
  })

  describe('validate', () => {
    it('end <= start → time_error', () => {
      expect(META.validate!({ start_time: 5, end_time: 5 })).toBe('video.cut.time_error')
    })

    it('end > start → null（合法）', () => {
      expect(META.validate!({ start_time: 0, end_time: 1 })).toBeNull()
    })

    it('雙 undefined → null（尚未填寫，非跨欄位錯誤）', () => {
      expect(META.validate!({})).toBeNull()
    })
  })

  describe('seedOnFileChange', () => {
    it('start 未定義 → end 填總長、start 補 0', () => {
      expect(META.seedOnFileChange!({ duration: 30 }, {})).toEqual({ end_time: 30, start_time: 0 })
    })

    it('start 已存在 → 只填 end，不覆蓋 start', () => {
      expect(META.seedOnFileChange!({ duration: 30 }, { start_time: 5 })).toEqual({ end_time: 30 })
    })

    it('fileInfo 為 null → null（不 seed）', () => {
      expect(META.seedOnFileChange!(null, {})).toBeNull()
    })

    it('duration 為 0（尚未載入完成）→ null（不 seed）', () => {
      expect(META.seedOnFileChange!({ duration: 0 }, {})).toBeNull()
    })
  })

  it('schema 不變量：每個 enum 欄位 default ∈ options（本 tool 無 enum 欄位，vacuously 過）', () => {
    for (const f of META.schema) {
      if (f.type === 'enum' && f.default !== undefined) {
        expect(f.options ?? []).toContain(f.default)
      }
    }
  })
})

describe('parseTimeToSeconds', () => {
  it('HH:MM:SS', () => {
    expect(parseTimeToSeconds('00:01:30')).toBe(90)
  })

  it('MM:SS', () => {
    expect(parseTimeToSeconds('01:30')).toBe(90)
  })

  it('純秒數字串', () => {
    expect(parseTimeToSeconds('90')).toBe(90)
  })

  it('空字串 → 0', () => {
    expect(parseTimeToSeconds('')).toBe(0)
  })
})

describe('secondsToTime', () => {
  it('90 → 00:01:30', () => {
    expect(secondsToTime(90)).toBe('00:01:30')
  })

  it('undefined → 00:00:00', () => {
    expect(secondsToTime(undefined)).toBe('00:00:00')
  })

  it('3661 → 01:01:01', () => {
    expect(secondsToTime(3661)).toBe('01:01:01')
  })

  it('90.7（小數截去）→ 00:01:30', () => {
    expect(secondsToTime(90.7)).toBe('00:01:30')
  })
})

describe('parseTimeToSeconds / secondsToTime roundtrip', () => {
  it('parseTimeToSeconds(secondsToTime(90)) === 90', () => {
    expect(parseTimeToSeconds(secondsToTime(90))).toBe(90)
  })
})
