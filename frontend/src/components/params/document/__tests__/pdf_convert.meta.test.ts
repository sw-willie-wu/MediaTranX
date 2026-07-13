/**
 * document.pdf_convert META 單測（統一參數元件 spec §4；批 4 Task 4.5 Part B）。
 * schema 準繩＝後端 PdfConvertRequest 全集（backend/app/api/routes/document/pdf_convert.py）：
 * output_format enum txt/md/images default 'txt'（file_id/suppress_results 由 host 注入，
 * 不入 schema）。images 僅 PDF 可用是 UI 層過濾（見 PdfConvertParams.vue），非 schema 裁剪。
 */
import { describe, it, expect } from 'vitest'
import { META } from '../pdf_convert.meta'

describe('document.pdf_convert META', () => {
  it('defaults() → { output_format: "txt" }', () => {
    expect(META.defaults()).toEqual({ output_format: 'txt' })
  })

  it('schema 欄位集合＝output_format（不含 file_id/suppress_results）', () => {
    expect(META.schema.map((f) => f.name)).toEqual(['output_format'])
  })

  it('schema 不變量：output_format default ∈ options，options 為後端全集 txt/md/images', () => {
    const f = META.schema.find((x) => x.name === 'output_format')!
    expect(f.options).toEqual(['txt', 'md', 'images'])
    expect(f.options).toContain(f.default)
  })

  it('multiSelect=true（舊 DocumentView pdf-convert case 走 submitToAll 批次）', () => {
    expect(META.multiSelect).toBe(true)
  })

  it('agentRequiresConfirm=false（沿舊 DocumentPdfConvertPanel.agentSchema.execute.requiresConfirm）', () => {
    expect(META.agentRequiresConfirm).toBe(false)
  })

  it('agentExecuteLabel="panel.doc_pdf_convert.execute"（沿舊 agentSchema.execute.label）', () => {
    expect(META.agentExecuteLabel).toBe('panel.doc_pdf_convert.execute')
  })

  it('無 seedOnFileChange/modelRequirement（不需模型，副檔名過濾留在 UI 層）', () => {
    expect(META.seedOnFileChange).toBeUndefined()
    expect(META.modelRequirement).toBeUndefined()
    expect(META.modelRequirements).toBeUndefined()
  })
})
