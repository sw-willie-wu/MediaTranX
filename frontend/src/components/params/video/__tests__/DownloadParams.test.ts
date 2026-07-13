/**
 * DownloadParams.vue 單測（統一參數元件 spec §5；批 2 Task 2.2）。
 * 覆蓋：url/title 文字欄 commit、format_intent dict 衍生 UI（mode 切 cap 顯示
 * max_height、清空移除 key、format_id 保留不動）、legacy scalar 正規化（掛載時
 * 若 format_intent 是字串/undefined → emit 一次正規化成 {mode:'auto'}）、
 * one-shot pattern（外部寫入重推 vs 自身回流不重推）。
 * video.download 是 pipeline-only source 節點，本元件只在 context='pipeline' 掛載，
 * 但仍照共用契約接受 params/context/fileInfo 三 prop。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import DownloadParams from '../DownloadParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import { hasParamComponent, METAS } from '../../index'

function mockT(k: string): string {
  return k
}

function mountParams(params: Record<string, unknown>, context: 'tool' | 'pipeline' = 'pipeline') {
  return mount(DownloadParams, {
    props: { params, context, fileInfo: null },
    global: {
      mocks: { $t: mockT },
    },
  })
}

function urlInput(w: ReturnType<typeof mountParams>) {
  return w.findAll('input[type="text"]')[0]
}

describe('DownloadParams 顯示', () => {
  it('mount → url 文字欄顯示 params.url', () => {
    const w = mountParams({ url: 'https://example.com/v', title: 'video', format_intent: { mode: 'auto' } })
    expect(urlInput(w).element.value).toBe('https://example.com/v')
  })

  it('params.url 未定義 → url 文字欄顯示空字串', () => {
    const w = mountParams({ title: 'video', format_intent: { mode: 'auto' } })
    expect(urlInput(w).element.value).toBe('')
  })

  it('mode="auto"（預設）→ max_height 輸入框不渲染', () => {
    const w = mountParams({ url: 'https://x', title: 'video', format_intent: { mode: 'auto' } })
    expect(w.findAll('input[type="number"]')).toHaveLength(0)
  })

  it('mode="cap" → max_height 輸入框渲染並顯示既有值', () => {
    const w = mountParams({ url: 'https://x', title: 'video', format_intent: { mode: 'cap', max_height: 720 } })
    const numberInputs = w.findAll('input[type="number"]')
    expect(numberInputs).toHaveLength(1)
    expect(numberInputs[0].element.value).toBe('720')
  })

  it('title 欄位（進階）顯示 params.title', () => {
    const w = mountParams({ url: 'https://x', title: 'my-video', format_intent: { mode: 'auto' } })
    const textInputs = w.findAll('input[type="text"]')
    // [0]=url,[1]=title
    expect(textInputs[1].element.value).toBe('my-video')
  })
})

describe('DownloadParams commit（欄位編輯 → emit）', () => {
  it('url 文字欄 change → emit update:params，其餘欄位保留', async () => {
    const w = mountParams({ url: 'https://old', title: 'video', format_intent: { mode: 'auto' } })
    await urlInput(w).setValue('https://new')

    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toEqual({
      url: 'https://new',
      title: 'video',
      format_intent: { mode: 'auto' },
    })
  })

  it('title 文字欄 change → emit update:params，url/format_intent 保留', async () => {
    const w = mountParams({ url: 'https://x', title: 'video', format_intent: { mode: 'auto' } })
    const titleInput = w.findAll('input[type="text"]')[1]
    await titleInput.setValue('renamed')

    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toEqual({
      url: 'https://x',
      title: 'renamed',
      format_intent: { mode: 'auto' },
    })
  })

  it('mode 切換為 cap → emit format_intent.mode="cap"，既有 max_height/format_id 保留', async () => {
    const w = mountParams({
      url: 'https://x', title: 'video',
      format_intent: { mode: 'auto', max_height: 480, format_id: 'itag-22' },
    })
    const select = w.findComponent(AppSelect)
    select.vm.$emit('update:modelValue', 'cap')
    await w.vm.$nextTick()

    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toEqual({
      url: 'https://x', title: 'video',
      format_intent: { mode: 'cap', max_height: 480, format_id: 'itag-22' },
    })
  })

  it('max_height 輸入 → emit format_intent.max_height 更新', async () => {
    const w = mountParams({ url: 'https://x', title: 'video', format_intent: { mode: 'cap', max_height: 480 } })
    const numberInput = w.findAll('input[type="number"]')[0]
    await numberInput.setValue('1080')

    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toEqual({
      url: 'https://x', title: 'video',
      format_intent: { mode: 'cap', max_height: 1080 },
    })
  })

  it('max_height 清空 → 從 format_intent 移除該 key（非設 undefined 殘留）', async () => {
    const w = mountParams({ url: 'https://x', title: 'video', format_intent: { mode: 'cap', max_height: 480 } })
    const numberInput = w.findAll('input[type="number"]')[0]
    await numberInput.setValue('')

    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    const fi = last.format_intent as Record<string, unknown>
    expect(fi).toEqual({ mode: 'cap' })
    expect('max_height' in fi).toBe(false)
  })
})

describe('DownloadParams — legacy 相容（format_intent 舊 scalar 正規化）', () => {
  it('params.format_intent 為字串（舊 recipe scalar）→ 掛載時 emit 一次正規化成 {mode:"auto"}', () => {
    const w = mountParams({ url: 'https://x', title: 'video', format_intent: 'auto' })
    expect(w.emitted('update:params')).toEqual([[
      { url: 'https://x', title: 'video', format_intent: { mode: 'auto' } },
    ]])
  })

  it('params.format_intent 為 undefined → 掛載時 emit 一次正規化成 {mode:"auto"}', () => {
    const w = mountParams({ url: 'https://x', title: 'video' })
    expect(w.emitted('update:params')).toEqual([[
      { url: 'https://x', title: 'video', format_intent: { mode: 'auto' } },
    ]])
  })

  it('params.format_intent 已是合法 dict → 掛載時不 emit', () => {
    const w = mountParams({ url: 'https://x', title: 'video', format_intent: { mode: 'cap', max_height: 720 } })
    expect(w.emitted('update:params')).toBeUndefined()
  })

  it('掛載時字串正規化後，UI 仍能正確顯示 mode="auto"（不因原始字串值渲染錯誤）', () => {
    const w = mountParams({ url: 'https://x', title: 'video', format_intent: 'auto' })
    const select = w.findComponent(AppSelect)
    expect(select.props('modelValue')).toBe('auto')
  })
})

describe('DownloadParams — 響應式衍生＋本地編輯不打斷（one-shot pattern）', () => {
  it('外部替換 props.params（rerender）→ url/title 顯示重推', async () => {
    const w = mountParams({ url: 'https://a', title: 'video', format_intent: { mode: 'auto' } })
    await w.setProps({ params: { url: 'https://b', title: 'renamed', format_intent: { mode: 'auto' } } })
    expect(urlInput(w).element.value).toBe('https://b')
    expect(w.findAll('input[type="text"]')[1].element.value).toBe('renamed')
  })

  it('自身 emit 回流（父層把同物件 set 回來）→ 使用者輸入中內容不被打斷', async () => {
    const w = mountParams({ url: 'https://a', title: 'video', format_intent: { mode: 'auto' } })
    await urlInput(w).setValue('https://committed')
    const emittedPayload = w.emitted('update:params')![w.emitted('update:params')!.length - 1][0] as Record<string, unknown>

    urlInput(w).element.value = 'in-progress-not-committed'
    await urlInput(w).trigger('input')

    await w.setProps({ params: emittedPayload })
    expect(urlInput(w).element.value).toBe('in-progress-not-committed')
  })

  it('one-shot：commit 後外部改值再改回原值，顯示仍須正確重推（不 stale）', async () => {
    const w = mountParams({ url: 'https://a', title: 'video', format_intent: { mode: 'auto' } })
    await urlInput(w).setValue('https://committed')
    expect(urlInput(w).element.value).toBe('https://committed')

    await w.setProps({ params: { url: 'https://other', title: 'video', format_intent: { mode: 'auto' } } })
    expect(urlInput(w).element.value).toBe('https://other')

    await w.setProps({ params: { url: 'https://committed', title: 'video', format_intent: { mode: 'auto' } } })
    expect(urlInput(w).element.value).toBe('https://committed')
  })
})

describe('params/index.ts 載入表', () => {
  it('hasParamComponent("video.download") === true', () => {
    expect(hasParamComponent('video.download')).toBe(true)
  })

  it('METAS["video.download"].toolKey === "video.download"', () => {
    expect(METAS['video.download'].toolKey).toBe('video.download')
  })
})
