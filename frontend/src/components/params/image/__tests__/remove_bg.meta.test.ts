/**
 * image.remove_bg META 單測（統一參數元件 spec §4；批 4 Task 4.3）。
 * schema 準繩＝後端 ImageRemoveBgRequest（backend/app/api/routes/image/remove_bg.py）：
 * mode default 'auto'（file_id/suppress_results 由 host 注入，不入 schema）。
 */
import { describe, it, expect } from 'vitest'
import { META } from '../remove_bg.meta'

describe('image.remove_bg META', () => {
  it('defaults() → { mode: "auto" }', () => {
    expect(META.defaults()).toEqual({ mode: 'auto' })
  })

  it('schema 欄位集合＝mode（不含 file_id/suppress_results）', () => {
    expect(META.schema.map((f) => f.name)).toEqual(['mode'])
  })

  it('schema 不變量：mode default ∈ options', () => {
    const mode = META.schema.find((f) => f.name === 'mode')!
    expect(mode.options).toEqual(['auto', 'person', 'product', 'animal', 'anime'])
    expect(mode.options).toContain(mode.default)
  })

  it('multiSelect=true（舊 ImageView remove-bg case 走 submitToAll 批次）', () => {
    expect(META.multiSelect).toBe(true)
  })

  it('agentExecuteLabel="panel.remove_bg.execute"（沿舊 agentSchema.execute.label）', () => {
    expect(META.agentExecuteLabel).toBe('panel.remove_bg.execute')
  })

  it('無 modelRequirement/modelRequirements（rembg 自備模型，preflight 恆真）', () => {
    expect(META.modelRequirement).toBeUndefined()
    expect(META.modelRequirements).toBeUndefined()
  })
})
