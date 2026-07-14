/**
 * image.compress META 單測（統一參數元件 spec §4；批 4 Task 4.1）。
 * 覆蓋 defaults() 與 schema 不變量；palette 動態上限/換圖重置等行為在 CompressParams.vue
 * 元件內（非 meta 層——meta.schema 對 gif_colors 無 default，見該檔檔頭註解），故不在此測。
 */
import { describe, it, expect } from 'vitest'
import { META } from '../compress.meta'

describe('image.compress META', () => {
  it('defaults() 只含有 default 的欄位；strength=75（偏離後端 60，沿工具頁 UI parity 決策）', () => {
    expect(META.defaults()).toEqual({
      strength: 75,
      gif_frame_drop: 0,
      gif_optimize_transparency: true,
      png_lossy: true,
      jpeg_progressive: true,
      jpeg_keep_metadata: false,
      webp_lossless: false,
    })
  })

  it('gif_colors 無 default（後端 Optional[int]=None=原調色盤）', () => {
    const f = META.schema.find((x) => x.name === 'gif_colors')!
    expect(f.default).toBeUndefined()
    expect(f.min).toBe(2)
    expect(f.max).toBe(256)
  })

  it('gif_frame_drop 型別為 number（非 enum——Surprise 12 裁決：schema 從後端）', () => {
    const f = META.schema.find((x) => x.name === 'gif_frame_drop')!
    expect(f.type).toBe('number')
    expect(f.min).toBe(0)
    expect(f.default).toBe(0)
  })

  it('png_lossy 為 boolean（非舊 png_mode enum）', () => {
    const f = META.schema.find((x) => x.name === 'png_lossy')!
    expect(f.type).toBe('boolean')
    expect(f.default).toBe(true)
  })

  it('schema 欄位集合＝後端全集 8 欄（不含 file_id/suppress_results）', () => {
    expect(META.schema.map((f) => f.name)).toEqual([
      'strength',
      'gif_colors',
      'gif_frame_drop',
      'gif_optimize_transparency',
      'png_lossy',
      'jpeg_progressive',
      'jpeg_keep_metadata',
      'webp_lossless',
    ])
  })

  it('strength 為唯一非 advanced（頂層）欄位', () => {
    const nonAdvanced = META.schema.filter((f) => !f.advanced).map((f) => f.name)
    expect(nonAdvanced).toEqual(['strength'])
  })

  it('schema 不變量：每個 enum 欄位 default ∈ options（本 tool 無 enum 欄位，vacuously 過）', () => {
    for (const f of META.schema) {
      if (f.type === 'enum' && f.default !== undefined) {
        expect(f.options ?? []).toContain(f.default)
      }
    }
  })

  it('multiSelect=true；agentExecuteLabel="panel.compress.execute"（≠ labelKey）', () => {
    expect(META.multiSelect).toBe(true)
    expect(META.agentExecuteLabel).toBe('panel.compress.execute')
    expect(META.labelKey).not.toBe(META.agentExecuteLabel)
  })

  it('無 validate/buildSubmit/modelRequirement/seedOnFileChange（沿舊 panel：無跨欄驗證、無端點分流、無模型、palette 邏輯收進元件）', () => {
    expect(META.validate).toBeUndefined()
    expect(META.buildSubmit).toBeUndefined()
    expect(META.modelRequirement).toBeUndefined()
    expect(META.modelRequirements).toBeUndefined()
    expect(META.seedOnFileChange).toBeUndefined()
  })
})
