/**
 * audio.volume META 單測（統一參數元件 spec §4；批 3 Task 3.1）。
 * 覆蓋 defaults/buildSubmit（歸零/labelKey 分流）＋ agentRequiresConfirm 選配欄位。
 */
import { describe, it, expect } from 'vitest'
import { META } from '../volume.meta'

describe('audio.volume META', () => {
  it('defaults() 只含有 default 的欄位', () => {
    expect(META.defaults()).toEqual({ volume_db: 0, normalize: false })
  })

  it('schema 不變量：無 enum 欄位（number/boolean 各一）', () => {
    for (const f of META.schema) {
      expect(f.type).not.toBe('enum')
    }
  })

  it('volume_db min/max 準繩＝後端 ge-30 le30（UI 滑桿另收斂為 ±20，見 Params 單測）', () => {
    const f = META.schema.find((x) => x.name === 'volume_db')!
    expect(f.min).toBe(-30)
    expect(f.max).toBe(30)
  })

  it('agentRequiresConfirm=false（沿舊 AudioVolumePanel），agentExecuteLabel 沿舊字串', () => {
    expect(META.agentRequiresConfirm).toBe(false)
    expect(META.agentExecuteLabel).toBe('panel.volume.execute')
  })

  describe('buildSubmit', () => {
    it('adjust 模式（normalize=false）→ volume_db 原樣送出，labelKey=adjust_label', () => {
      const spec = META.buildSubmit!({ volume_db: 12, normalize: false })
      expect(spec).toEqual({
        apiPath: '/audio/volume',
        payload: { volume_db: 12, normalize: false },
        taskType: 'audio.volume',
        labelKey: 'audio.volume.adjust_label',
      })
    })

    it('normalize 模式（normalize=true）→ volume_db 歸 0，labelKey=normalize_label（鏡射舊 getParams）', () => {
      const spec = META.buildSubmit!({ volume_db: -15, normalize: true })
      expect(spec).toEqual({
        apiPath: '/audio/volume',
        payload: { volume_db: 0, normalize: true },
        taskType: 'audio.volume',
        labelKey: 'audio.volume.normalize_label',
      })
    })

    it('volume_db 未設 + adjust 模式 → 送 0（Number(undefined ?? 0)）', () => {
      const spec = META.buildSubmit!({ normalize: false })
      expect(spec.payload.volume_db).toBe(0)
    })

    it('payload 一律不含 file_id', () => {
      for (const normalize of [true, false]) {
        const spec = META.buildSubmit!({ volume_db: 5, normalize })
        expect(spec.payload).not.toHaveProperty('file_id')
      }
    })
  })

  describe('visibleWhen', () => {
    it('volume_db：normalize=true 時不可見，其餘可見', () => {
      const f = META.schema.find((x) => x.name === 'volume_db')!
      expect(f.visibleWhen!({ normalize: false })).toBe(true)
      expect(f.visibleWhen!({})).toBe(true)
      expect(f.visibleWhen!({ normalize: true })).toBe(false)
    })
  })
})
