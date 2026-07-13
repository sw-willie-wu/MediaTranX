/**
 * SplitParams.vue 單測（統一參數元件 spec §5；批 4 Task 4.5 Part A）。
 * 覆蓋：顯示、one-shot lastEmitted pattern（外部寫入重推 vs 自身回流不重推）、commit 語意
 * （@change 才 emit，沿 CutParams/DownloadParams 慣例）、params/index.ts 載入表。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import SplitParams from '../SplitParams.vue'
import { hasParamComponent, METAS } from '../../index'

function mountParams(params: Record<string, unknown>, context: 'tool' | 'pipeline' = 'tool') {
  return mount(SplitParams, {
    props: { params, context, fileInfo: null },
    global: { mocks: { $t: (k: string) => k } },
  })
}

function pagesInput(w: ReturnType<typeof mountParams>) {
  return w.find('input[type="text"]')
}

describe('SplitParams 顯示', () => {
  it('mount → 文字欄顯示 params.pages', () => {
    const w = mountParams({ pages: '1-3,5' })
    expect(pagesInput(w).element.value).toBe('1-3,5')
  })

  it('params.pages 未定義 → 文字欄顯示空字串', () => {
    const w = mountParams({})
    expect(pagesInput(w).element.value).toBe('')
  })
})

describe('SplitParams commit（欄位編輯 → emit）', () => {
  it('文字欄 change → emit update:params 恰含新 pages', async () => {
    const w = mountParams({ pages: '' })
    await pagesInput(w).setValue('1-3,7-9')

    expect(w.emitted('update:params')).toEqual([[{ pages: '1-3,7-9' }]])
  })

  it('commit 保留 params 其他既有鍵（雖 schema 只有 pages，驗證 spread 語意）', async () => {
    const w = mountParams({ pages: '', extra: 'kept' })
    await pagesInput(w).setValue('2-4')

    expect(w.emitted('update:params')![0][0]).toEqual({ pages: '2-4', extra: 'kept' })
  })
})

describe('SplitParams — 響應式衍生＋本地編輯不打斷（one-shot pattern）', () => {
  it('外部替換 props.params（rerender）→ 文字欄顯示重推', async () => {
    const w = mountParams({ pages: '1-3' })
    await w.setProps({ params: { pages: '5-8' } })
    expect(pagesInput(w).element.value).toBe('5-8')
  })

  it('自身 emit 回流（父層把同物件 set 回來）→ 使用者輸入中內容不被打斷', async () => {
    const w = mountParams({ pages: '1-3' })
    await pagesInput(w).setValue('9-10')
    const emittedPayload = w.emitted('update:params')![0][0] as Record<string, unknown>

    pagesInput(w).element.value = 'in-progress-not-committed'
    await pagesInput(w).trigger('input')

    await w.setProps({ params: emittedPayload })
    expect(pagesInput(w).element.value).toBe('in-progress-not-committed')
  })

  it('one-shot：commit 後外部改值再改回原值，顯示仍須正確重推（不 stale）', async () => {
    const w = mountParams({ pages: '1-3' })
    await pagesInput(w).setValue('committed-val')
    expect(pagesInput(w).element.value).toBe('committed-val')

    await w.setProps({ params: { pages: 'other-val' } })
    expect(pagesInput(w).element.value).toBe('other-val')

    await w.setProps({ params: { pages: 'committed-val' } })
    expect(pagesInput(w).element.value).toBe('committed-val')
  })
})

describe('params/index.ts 載入表', () => {
  it('hasParamComponent("document.split") === true', () => {
    expect(hasParamComponent('document.split')).toBe(true)
  })

  it('METAS["document.split"].toolKey === "document.split"', () => {
    expect(METAS['document.split'].toolKey).toBe('document.split')
  })
})
