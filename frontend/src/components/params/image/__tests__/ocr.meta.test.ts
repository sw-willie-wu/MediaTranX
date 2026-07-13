/**
 * image.ocr META 單測（統一參數元件 spec §4；批 4 Task 4.4）。
 * 本工具的 schema/modelRequirement 完全由 document/ocr.meta.ts 的 buildOcrMeta() 工廠產生
 * （見該檔／image/ocr.meta.ts 檔頭註解）——此處只覆蓋隨掛載點變化的欄位，schema 語意本身
 * 已由 document/__tests__/ocr.meta.test.ts 涵蓋，不重複整組斷言。
 */
import { describe, it, expect } from 'vitest'
import { META, encodeModelToken, decodeModelToken } from '../ocr.meta'
import { META as DOC_OCR_META } from '../../document/ocr.meta'

describe('image.ocr META', () => {
  it('toolKey/apiPath/labelKey/taskType 隨掛載點（與 document.ocr 不同）', () => {
    expect(META.toolKey).toBe('image.ocr')
    expect(META.apiPath).toBe('/image/ocr')
    expect(META.labelKey).toBe('image.ocr.task_label')
    expect(META.taskType).toBe('image.ocr')
  })

  it('agentExecuteLabel = panel.ocr.execute（沿舊 ImageOcrPanel，與 document.ocr 的 panel.doc_ocr.execute 不同）', () => {
    expect(META.agentExecuteLabel).toBe('panel.ocr.execute')
    expect(META.agentExecuteLabel).not.toBe(DOC_OCR_META.agentExecuteLabel)
  })

  it('schema 與 document.ocr 完全相同（共用工廠，同一份欄位定義）', () => {
    expect(META.schema).toEqual(DOC_OCR_META.schema)
  })

  it('defaults()/downloadFormatField/multiSelect/persistedModelFields 與 document.ocr 相同', () => {
    expect(META.defaults()).toEqual(DOC_OCR_META.defaults())
    expect(META.downloadFormatField).toBe(DOC_OCR_META.downloadFormatField)
    expect(META.multiSelect).toBe(DOC_OCR_META.multiSelect)
    expect(META.persistedModelFields).toEqual(DOC_OCR_META.persistedModelFields)
  })

  it('modelRequirement 行為與 document.ocr 一致（共用同一純函式邏輯）', () => {
    expect(META.modelRequirement!({ remote: false, model_family: 'gemma4', model_size: '9b' }))
      .toEqual(DOC_OCR_META.modelRequirement!({ remote: false, model_family: 'gemma4', model_size: '9b' }))
    expect(META.modelRequirement!({ remote: true })).toBeNull()
  })

  it('re-export encodeModelToken/decodeModelToken 與 document 版同一函式（同純函式邏輯）', () => {
    expect(encodeModelToken({ remote: false, model_family: 'qwen3vl', model_size: '4b' })).toBe('qwen3vl:4b')
    expect(decodeModelToken('qwen3vl:4b').model_family).toBe('qwen3vl')
  })
})
