/**
 * video.download META 單測（統一參數元件 spec §4；批 2 Task 2.2）。
 * schema 準繩＝後端 DownloadRequest（backend/app/schemas/video_download.py）：
 * url:str 必填、title:str="video"、format_intent:FormatIntent（巢狀 dict，
 * mode:'auto'|'cap'|'ask'='auto'、max_height:Optional[int]、format_id:Optional[str]）。
 * video.download 是 registry 唯一 source 節點——無 seedOnFileChange/modelRequirement。
 */
import { describe, it, expect } from 'vitest'
import { META } from '../download.meta'

describe('video.download META', () => {
  it('schema 欄位集合＝url/title/format_intent（不含 file_id/suppress_results）', () => {
    expect(META.schema.map((f) => f.name)).toEqual(['url', 'title', 'format_intent'])
  })

  it('url 欄位無 default（必填語意靠 validate）', () => {
    const url = META.schema.find((f) => f.name === 'url')!
    expect(url.type).toBe('string')
    expect(url.default).toBeUndefined()
    expect(url.advanced).toBeFalsy()
  })

  it('title 欄位 default="video"，advanced（舊 UI 無此欄）', () => {
    const title = META.schema.find((f) => f.name === 'title')!
    expect(title.type).toBe('string')
    expect(title.default).toBe('video')
    expect(title.advanced).toBe(true)
  })

  it('format_intent 欄位 type=dict、default={mode:"auto"}、advanced，不設 agentHint', () => {
    const fi = META.schema.find((f) => f.name === 'format_intent')!
    expect(fi.type).toBe('dict')
    expect(fi.default).toEqual({ mode: 'auto' })
    expect(fi.advanced).toBe(true)
    expect(fi.agentHint).toBeUndefined()
  })

  it('defaults() 含 title/format_intent（url 無 default，不出現在 defaults）', () => {
    expect(META.defaults()).toEqual({ title: 'video', format_intent: { mode: 'auto' } })
  })

  describe('validate', () => {
    it('url 未定義 → url_error', () => {
      expect(META.validate!({})).toBe('video.download.url_error')
    })

    it('url 為空字串 → url_error', () => {
      expect(META.validate!({ url: '' })).toBe('video.download.url_error')
    })

    it('url 為空白字串 → url_error', () => {
      expect(META.validate!({ url: '   ' })).toBe('video.download.url_error')
    })

    it('url 非 http(s) 開頭 → url_error', () => {
      expect(META.validate!({ url: 'ftp://example.com/video' })).toBe('video.download.url_error')
    })

    it('url 為合法 http(s) → null（合法）', () => {
      expect(META.validate!({ url: 'https://example.com/video' })).toBeNull()
      expect(META.validate!({ url: 'http://example.com/video' })).toBeNull()
    })
  })

  it('multiSelect=false', () => {
    expect(META.multiSelect).toBe(false)
  })

  it('無 seedOnFileChange/modelRequirement（source 節點無檔案、無模型需求）', () => {
    expect(META.seedOnFileChange).toBeUndefined()
    expect(META.modelRequirement).toBeUndefined()
  })

  it('schema 不變量：無 enum 欄位（vacuously 過 default∈options 檢查）', () => {
    for (const f of META.schema) {
      if (f.type === 'enum' && f.default !== undefined) {
        expect(f.options ?? []).toContain(f.default)
      }
    }
  })

  it('toolKey/apiPath/labelKey/taskType 對齊 registry 現值', () => {
    expect(META.toolKey).toBe('video.download')
    expect(META.apiPath).toBe('/video/download')
    expect(META.labelKey).toBe('video.download.task_label')
    expect(META.taskType).toBe('video.download')
  })
})
