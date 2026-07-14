/**
 * audio.separate META 單測（統一參數元件 spec §4；批 3 Task 3.3）。
 * 覆蓋 defaults（stems 無 default）/ validate（空陣列擋、undefined 放行）/
 * modelRequirement（variant 型，slot=separate/family=demucs/categories=['separate']）。
 */
import { describe, it, expect } from 'vitest'
import { META } from '../separate.meta'

describe('audio.separate META', () => {
  it('defaults() 只含有 default 的欄位（stems 無 default，不出現）', () => {
    expect(META.defaults()).toEqual({
      model_name: 'htdemucs_6s',
      output_format: 'wav',
      generate_midi: false,
    })
    expect(META.defaults()).not.toHaveProperty('stems')
  })

  it('schema 含 stems（type=list, itemType=string）', () => {
    const f = META.schema.find((x) => x.name === 'stems')!
    expect(f.type).toBe('list')
    expect(f.itemType).toBe('string')
    expect(f.default).toBeUndefined()
  })

  it('model_name 為 advanced enum，唯一選項 htdemucs_6s', () => {
    const f = META.schema.find((x) => x.name === 'model_name')!
    expect(f.type).toBe('enum')
    expect(f.options).toEqual(['htdemucs_6s'])
    expect(f.advanced).toBe(true)
  })

  it('agentExecuteLabel 沿舊字串；agentRequiresConfirm 不設（退回 host 預設 true）', () => {
    expect(META.agentExecuteLabel).toBe('panel.separate.execute')
    expect(META.agentRequiresConfirm).toBeUndefined()
  })

  describe('validate', () => {
    it('stems 為空陣列 → 回 i18n 錯誤 key（鏡射舊 isDisabled selectedStems.length===0）', () => {
      expect(META.validate!({ stems: [] })).toBe('audio.separate.no_stems_selected')
    })

    it('stems 未設（undefined）→ 合法（=後端 None=全部）', () => {
      expect(META.validate!({})).toBeNull()
    })

    it('stems 非空陣列 → 合法', () => {
      expect(META.validate!({ stems: ['vocals', 'drums'] })).toBeNull()
    })
  })

  describe('modelRequirement', () => {
    it('variant 型：slot=separate, family=demucs, categories=[separate]，variant 取 model_name', () => {
      expect(META.modelRequirement!({ model_name: 'htdemucs_6s' })).toEqual({
        slot: 'separate',
        family: 'demucs',
        variant: 'htdemucs_6s',
        categories: ['separate'],
      })
    })

    it('model_name 未設 → variant 退回 htdemucs_6s（default）', () => {
      expect(META.modelRequirement!({})).toEqual({
        slot: 'separate',
        family: 'demucs',
        variant: 'htdemucs_6s',
        categories: ['separate'],
      })
    })
  })

  it('multiSelect: true（沿舊 AudioView.handleMultiExecute 支援批次）', () => {
    expect(META.multiSelect).toBe(true)
  })
})
