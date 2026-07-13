/**
 * PdfConvertParams.vue 單測（統一參數元件 spec §5；批 4 Task 4.5 Part B）。
 * 覆蓋：顯示（options 依 currentFileExt 動態過濾 images）、選擇 → emit update:params、
 * 非 PDF＋殘留 output_format='images' 防 stale 修正、params/index.ts 載入表。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import PdfConvertParams from '../PdfConvertParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import { hasParamComponent, METAS } from '../../index'

function mountParams(
  params: Record<string, unknown>,
  opts: { currentFileExt?: string; context?: 'tool' | 'pipeline' } = {},
) {
  return mount(PdfConvertParams, {
    props: {
      params,
      context: opts.context ?? 'tool',
      fileInfo: null,
      currentFileExt: opts.currentFileExt,
    },
    global: { mocks: { $t: (k: string) => k } },
  })
}

describe('PdfConvertParams 顯示', () => {
  it('mount params={output_format:"md"} → AppSelect modelValue 為 md', () => {
    const w = mountParams({ output_format: 'md' }, { currentFileExt: 'pdf' })
    const select = w.findComponent(AppSelect)
    expect(select.props('modelValue')).toBe('md')
  })

  it('params.output_format 未定義 → 落回 txt', () => {
    const w = mountParams({}, { currentFileExt: 'pdf' })
    const select = w.findComponent(AppSelect)
    expect(select.props('modelValue')).toBe('txt')
  })

  it('currentFileExt="pdf" → options 含 images（txt/md/images）', () => {
    const w = mountParams({ output_format: 'txt' }, { currentFileExt: 'pdf' })
    const select = w.findComponent(AppSelect)
    const opts = (select.props('options') as Array<{ value: string }>).map((o) => o.value)
    expect(opts).toEqual(['txt', 'md', 'images'])
  })

  it('currentFileExt="docx"（非 pdf）→ options 排除 images（僅 txt/md）', () => {
    const w = mountParams({ output_format: 'txt' }, { currentFileExt: 'docx' })
    const select = w.findComponent(AppSelect)
    const opts = (select.props('options') as Array<{ value: string }>).map((o) => o.value)
    expect(opts).toEqual(['txt', 'md'])
  })

  it('currentFileExt 未傳（pipeline context 常見，副檔名未知）→ 與 legacy 表單 parity，options 含全部三個（txt/md/images）', () => {
    const w = mountParams({ output_format: 'txt' })
    const select = w.findComponent(AppSelect)
    const opts = (select.props('options') as Array<{ value: string }>).map((o) => o.value)
    expect(opts).toEqual(['txt', 'md', 'images'])
  })
})

describe('PdfConvertParams commit（選擇 → emit）', () => {
  it('選擇 output_format → emit update:params 恰含新值', async () => {
    const w = mountParams({ output_format: 'txt' }, { currentFileExt: 'pdf' })
    const select = w.findComponent(AppSelect)
    select.vm.$emit('update:modelValue', 'images')
    await w.vm.$nextTick()

    expect(w.emitted('update:params')).toEqual([[{ output_format: 'images' }]])
  })

  it('選擇 → 保留 params 其他既有鍵', async () => {
    const w = mountParams({ output_format: 'txt', extra: 'kept' }, { currentFileExt: 'pdf' })
    const select = w.findComponent(AppSelect)
    select.vm.$emit('update:modelValue', 'md')
    await w.vm.$nextTick()

    expect(w.emitted('update:params')![0][0]).toEqual({ output_format: 'md', extra: 'kept' })
  })
})

describe('PdfConvertParams — 非 PDF＋殘留 images 防 stale', () => {
  it('掛載時 currentFileExt≠pdf 且 params.output_format="images" → 立即 emit 修正回 txt', () => {
    const w = mountParams({ output_format: 'images' }, { currentFileExt: 'docx' })
    expect(w.emitted('update:params')).toEqual([[{ output_format: 'txt' }]])
  })

  it('掛載時 currentFileExt=pdf 且 output_format="images" → 不 emit（合法值）', () => {
    const w = mountParams({ output_format: 'images' }, { currentFileExt: 'pdf' })
    expect(w.emitted('update:params')).toBeUndefined()
  })

  it('掛載時已是合法值（非 images）→ 不 emit', () => {
    const w = mountParams({ output_format: 'txt' }, { currentFileExt: 'docx' })
    expect(w.emitted('update:params')).toBeUndefined()
  })

  it('掛載後切檔從 pdf → 非 pdf（output_format 仍是 images）→ emit 修正回 txt', async () => {
    const w = mountParams({ output_format: 'images' }, { currentFileExt: 'pdf' })
    expect(w.emitted('update:params')).toBeUndefined()

    await w.setProps({ currentFileExt: 'docx' })

    expect(w.emitted('update:params')).toEqual([[{ output_format: 'txt' }]])
  })

  it('pipeline context＋currentFileExt 未傳＋params.output_format="images" 掛載 → 不 emit 修正（副檔名未知不可誤改 recipe），且 options 三選項都在', () => {
    const w = mountParams({ output_format: 'images' }, { context: 'pipeline' })
    expect(w.emitted('update:params')).toBeUndefined()

    const select = w.findComponent(AppSelect)
    const opts = (select.props('options') as Array<{ value: string }>).map((o) => o.value)
    expect(opts).toEqual(['txt', 'md', 'images'])
  })
})

describe('params/index.ts 載入表', () => {
  it('hasParamComponent("document.pdf_convert") === true', () => {
    expect(hasParamComponent('document.pdf_convert')).toBe(true)
  })

  it('METAS["document.pdf_convert"].toolKey === "document.pdf_convert"', () => {
    expect(METAS['document.pdf_convert'].toolKey).toBe('document.pdf_convert')
  })
})
