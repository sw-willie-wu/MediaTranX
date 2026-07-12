/**
 * audio.cut META 單測（統一參數元件 spec §4；批 3 Task 3.2）。
 * 覆蓋 defaults/validate/seedOnFileChange/timeToSeconds roundtrip。
 */
import { describe, it, expect } from 'vitest'
import { META, timeToSeconds, secondsToTime } from '../cut.meta'

describe('audio.cut META', () => {
  it('defaults() 只含有 default 的欄位（end_time 無 default，後端必填）', () => {
    expect(META.defaults()).toEqual({ start_time: '00:00:00' })
  })

  it('schema：start_time/end_time 皆為 string，agentHint=HH:MM:SS', () => {
    const start = META.schema.find((f) => f.name === 'start_time')!
    const end = META.schema.find((f) => f.name === 'end_time')!
    expect(start.type).toBe('string')
    expect(start.default).toBe('00:00:00')
    expect(start.agentHint).toBe('HH:MM:SS')
    expect(end.type).toBe('string')
    expect(end.default).toBeUndefined()
    expect(end.agentHint).toBe('HH:MM:SS')
  })

  it('agentRequiresConfirm/agentExecuteLabel 皆未設（舊 panel 無 agentSchema，退回 host 預設）', () => {
    expect(META.agentRequiresConfirm).toBeUndefined()
    expect(META.agentExecuteLabel).toBeUndefined()
  })

  it('multiSelect: false（每檔起止不同，不支援批次，沿舊 panel）', () => {
    expect(META.multiSelect).toBe(false)
  })

  describe('validate', () => {
    it('end_time 未設 → time_error', () => {
      expect(META.validate!({ start_time: '00:00:00' })).toBe('audio.cut.time_error')
    })

    it('end_time 空字串 → time_error', () => {
      expect(META.validate!({ start_time: '00:00:00', end_time: '' })).toBe('audio.cut.time_error')
    })

    it('end_time 空白字串（只有空格）→ time_error', () => {
      expect(META.validate!({ start_time: '00:00:00', end_time: '   ' })).toBe('audio.cut.time_error')
    })

    it('end <= start → time_error', () => {
      expect(META.validate!({ start_time: '00:01:00', end_time: '00:01:00' })).toBe('audio.cut.time_error')
      expect(META.validate!({ start_time: '00:01:00', end_time: '00:00:30' })).toBe('audio.cut.time_error')
    })

    it('end > start → null（合法）', () => {
      expect(META.validate!({ start_time: '00:00:10', end_time: '00:01:00' })).toBeNull()
    })

    it('start_time 未設 → 視為 00:00:00 比較', () => {
      expect(META.validate!({ end_time: '00:00:01' })).toBeNull()
      expect(META.validate!({ end_time: '00:00:00' })).toBe('audio.cut.time_error')
    })
  })

  describe('seedOnFileChange', () => {
    it('duration=100 → start=20%、end=80%', () => {
      expect(META.seedOnFileChange!({ duration: 100 }, {})).toEqual({
        start_time: '00:00:20',
        end_time: '00:01:20',
      })
    })

    it('無 duration → null', () => {
      expect(META.seedOnFileChange!({}, {})).toBeNull()
      expect(META.seedOnFileChange!(null, {})).toBeNull()
    })

    it('duration<=0 → null', () => {
      expect(META.seedOnFileChange!({ duration: 0 }, {})).toBeNull()
      expect(META.seedOnFileChange!({ duration: -5 }, {})).toBeNull()
    })

    it('無條件重填（鏡射舊 watch(duration,immediate)）：current 已有值也照樣覆蓋', () => {
      expect(
        META.seedOnFileChange!({ duration: 100 }, { start_time: '00:00:05', end_time: '00:00:50' }),
      ).toEqual({ start_time: '00:00:20', end_time: '00:01:20' })
    })
  })

  describe('timeToSeconds / secondsToTime roundtrip', () => {
    it('HH:MM:SS → 秒 → HH:MM:SS roundtrip', () => {
      for (const t of ['00:00:00', '00:01:30', '01:02:03', '23:59:59']) {
        expect(secondsToTime(timeToSeconds(t))).toBe(t)
      }
    })

    it('timeToSeconds 支援 MM:SS 與純數字字串（沿舊 panel）', () => {
      expect(timeToSeconds('01:30')).toBe(90)
      expect(timeToSeconds('90')).toBe(90)
    })

    it('timeToSeconds 非法字串 → 0', () => {
      expect(timeToSeconds('abc')).toBe(0)
      expect(timeToSeconds('')).toBe(0)
    })

    it('secondsToTime(undefined) → 00:00:00', () => {
      expect(secondsToTime(undefined)).toBe('00:00:00')
    })

    it('secondsToTime 負數/NaN → 00:00:00', () => {
      expect(secondsToTime(-5)).toBe('00:00:00')
      expect(secondsToTime(NaN)).toBe('00:00:00')
    })
  })
})
