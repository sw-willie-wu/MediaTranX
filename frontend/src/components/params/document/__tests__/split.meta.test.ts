/**
 * document.split META 單測（統一參數元件 spec §4；批 4 Task 4.5 Part A）。
 * schema 準繩＝後端 DocumentSplitRequest（backend/app/api/routes/document/split.py）：
 * pages default ''（file_id/suppress_results 由 host 注入，不入 schema）。
 */
import { describe, it, expect } from 'vitest'
import { META } from '../split.meta'

describe('document.split META', () => {
  it('defaults() → { pages: "" }', () => {
    expect(META.defaults()).toEqual({ pages: '' })
  })

  it('schema 欄位集合＝pages（不含 file_id/suppress_results）', () => {
    expect(META.schema.map((f) => f.name)).toEqual(['pages'])
  })

  it('multiSelect=true（舊 DocumentView split case 走 submitToAll 批次）', () => {
    expect(META.multiSelect).toBe(true)
  })

  it('agentRequiresConfirm=false（沿舊 DocumentSplitPanel.agentSchema.execute.requiresConfirm）', () => {
    expect(META.agentRequiresConfirm).toBe(false)
  })

  it('agentExecuteLabel="panel.doc_split.execute"（沿舊 agentSchema.execute.label）', () => {
    expect(META.agentExecuteLabel).toBe('panel.doc_split.execute')
  })

  describe('seedOnFileChange（鏡射舊 watch(fileId → 清空 pages)）', () => {
    it('無條件回傳 { pages: "" }——不論傳入 fileInfo/current 內容為何', () => {
      expect(META.seedOnFileChange!({ fileId: 'a' }, { pages: '1-3' })).toEqual({ pages: '' })
      expect(META.seedOnFileChange!(null, { pages: '5-8' })).toEqual({ pages: '' })
      expect(META.seedOnFileChange!({ fileId: 'b' }, {})).toEqual({ pages: '' })
    })
  })

  it('schema 不變量：無 enum 欄位（vacuously 過）', () => {
    for (const f of META.schema) {
      if (f.type === 'enum' && f.default !== undefined) {
        expect(f.options ?? []).toContain(f.default)
      }
    }
  })
})
