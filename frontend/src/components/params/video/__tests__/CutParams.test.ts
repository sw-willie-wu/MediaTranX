/**
 * CutParams.vue 單測（統一參數元件 spec §5；Task 0.4）。
 * 覆蓋顯示字串響應式衍生＋本地編輯不打斷 pattern（之後 25 個元件共用的核心）。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CutParams from '../CutParams.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import { hasParamComponent, METAS } from '../../index'

function mockT(k: string): string {
  return k
}

function mountParams(params: Record<string, unknown>, context: 'tool' | 'pipeline' = 'tool') {
  return mount(CutParams, {
    props: { params, context, fileInfo: null },
    global: {
      mocks: { $t: mockT },
    },
  })
}

describe('CutParams 顯示', () => {
  it('mount 秒數 → 兩輸入框顯示 HH:MM:SS', () => {
    const w = mountParams({ start_time: 90, end_time: 120, stream_copy: true })
    const inputs = w.findAll('input[type="text"]')
    expect(inputs[0].element.value).toBe('00:01:30')
    expect(inputs[1].element.value).toBe('00:02:00')
  })

  it('params={}（無值）→ 顯示 00:00:00/00:00:00', () => {
    const w = mountParams({})
    const inputs = w.findAll('input[type="text"]')
    expect(inputs[0].element.value).toBe('00:00:00')
    expect(inputs[1].element.value).toBe('00:00:00')
  })
})

describe('CutParams commit（本地編輯 → emit）', () => {
  it('start 輸入框 setValue+change → emit update:params 恰一次、payload 正確', async () => {
    const w = mountParams({ start_time: 90, end_time: 120, stream_copy: true })
    const startInput = w.findAll('input[type="text"]')[0]
    // setValue 內部已 trigger 'input'+'change'；'input' 只動本地 ref（v-model），
    // 'change' 才會呼叫 commitField → emit，故整體恰好 emit 一次。
    await startInput.setValue('00:00:10')

    expect(w.emitted('update:params')).toHaveLength(1)
    expect(w.emitted('update:params')![0][0]).toEqual({
      start_time: 10,
      end_time: 120,
      stream_copy: true,
    })
  })

  it('stream_copy toggle → emit payload stream_copy:false、時間欄位保留', async () => {
    const w = mountParams({ start_time: 90, end_time: 120, stream_copy: true })
    const appToggle = w.findComponent(AppToggle)
    appToggle.vm.$emit('update:modelValue', false)
    await w.vm.$nextTick()

    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toEqual({
      start_time: 90,
      end_time: 120,
      stream_copy: false,
    })
  })
})

describe('CutParams 響應式衍生＋本地編輯不打斷', () => {
  it('外部替換 props.params（rerender）→ 顯示字串重推', async () => {
    const w = mountParams({ start_time: 90, end_time: 120, stream_copy: true })
    await w.setProps({ params: { start_time: 30, end_time: 120, stream_copy: true } })
    const inputs = w.findAll('input[type="text"]')
    expect(inputs[0].element.value).toBe('00:00:30')
  })

  it('自身 emit 回流不重推顯示字串（父層把同物件 set 回來）', async () => {
    const w = mountParams({ start_time: 90, end_time: 120, stream_copy: true })
    const startInput = w.findAll('input[type="text"]')[0]
    // setValue 內部會連 trigger 'input'+'change'（即 commit），故先用 setValue 做一次正規 commit。
    await startInput.setValue('00:00:10')

    const emittedPayload = w.emitted('update:params')![0][0] as Record<string, unknown>

    // 使用者接著又打了一個非正規格式（模擬正在輸入中——只 trigger 'input'，不 commit）
    startInput.element.value = 'bogus-in-progress'
    await startInput.trigger('input')

    // 父層把「上次自己 emit 的同一份 payload」set 回來（回流）
    await w.setProps({ params: emittedPayload })

    // 顯示字串不應被重算成 secondsToTime(...)，使用者輸入中的內容應保留
    expect(startInput.element.value).toBe('bogus-in-progress')
  })

  it('one-shot：commit 後外部改值再改回原值，顯示字串仍須正確重推（不 stale）', async () => {
    const w = mountParams({ start_time: 90, end_time: 120, stream_copy: true })
    const startInput = w.findAll('input[type="text"]')[0]

    // 使用者 commit 一次（lastEmitted = {start_time:10,...}）
    await startInput.setValue('00:00:10')
    expect(startInput.element.value).toBe('00:00:10')

    // 外部把值改成別的（90 秒），顯示字串應重推成 00:01:30
    await w.setProps({ params: { start_time: 90, end_time: 120, stream_copy: true } })
    expect(startInput.element.value).toBe('00:01:30')

    // 外部又把值改回一開始 commit 的那個值（10 秒）——
    // 舊版 bug：lastEmitted 從未被清空，這裡會被誤判成「自身 emit 回流」而跳過重推，顯示卡在 00:01:30。
    // 修復後 lastEmitted 已在上一次 watch 觸發時被消費（設回 null），這次必須正常重推成 00:00:10。
    await w.setProps({ params: { start_time: 10, end_time: 120, stream_copy: true } })
    expect(startInput.element.value).toBe('00:00:10')
  })
})

describe('CutParams commitField 顯示正規化', () => {
  it('setValue("90") change 後輸入框顯示正規化為 00:01:30、emit payload start_time=90', async () => {
    const w = mountParams({ start_time: 0, end_time: 120, stream_copy: true })
    const startInput = w.findAll('input[type="text"]')[0]

    await startInput.setValue('90')

    expect(startInput.element.value).toBe('00:01:30')
    expect(w.emitted('update:params')).toHaveLength(1)
    expect(w.emitted('update:params')![0][0]).toEqual({
      start_time: 90,
      end_time: 120,
      stream_copy: true,
    })
  })
})

describe('params/index.ts 載入表', () => {
  it('hasParamComponent("video.cut") === true', () => {
    expect(hasParamComponent('video.cut')).toBe(true)
  })

  it('hasParamComponent("video.transcode") === true（批 1 Task 1.2 起已註冊）', () => {
    expect(hasParamComponent('video.transcode')).toBe(true)
  })

  it('METAS["video.cut"].toolKey === "video.cut"', () => {
    expect(METAS['video.cut'].toolKey).toBe('video.cut')
  })
})
