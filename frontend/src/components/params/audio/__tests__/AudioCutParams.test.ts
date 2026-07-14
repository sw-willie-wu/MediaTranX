/**
 * AudioCutParams.vue 單測（統一參數元件 spec §5；批 3 Task 3.2）。
 * 覆蓋顯示字串響應式衍生＋本地編輯不打斷（沿 CutParams.vue 核心 pattern）、
 * 出向比例 emit（watch params → update:trimRange）、入向 notify 寫 params、
 * 防迴圈（入向後不立刻反射出向）、pipeline 語境無 trim 通道行為。
 */
import { describe, it, expect } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AudioCutParams from '../AudioCutParams.vue'
import { hasParamComponent, METAS } from '../../index'

function mockT(k: string): string {
  return k
}

function mountParams(
  params: Record<string, unknown>,
  context: 'tool' | 'pipeline' = 'tool',
  fileInfo: Record<string, unknown> | null = null,
) {
  return mount(AudioCutParams, {
    props: { params, context, fileInfo },
    global: {
      mocks: { $t: mockT },
    },
  })
}

describe('AudioCutParams 顯示', () => {
  it('params 字串直接顯示（無需 secondsToTime 轉換——後端合約本身就是 HH:MM:SS）', () => {
    const w = mountParams({ start_time: '00:01:30', end_time: '00:02:00' })
    const inputs = w.findAll('input[type="text"]')
    expect(inputs[0].element.value).toBe('00:01:30')
    expect(inputs[1].element.value).toBe('00:02:00')
  })

  it('params={}（無值）→ start 顯示 00:00:00、end 顯示空字串（無 default）', () => {
    const w = mountParams({})
    const inputs = w.findAll('input[type="text"]')
    expect(inputs[0].element.value).toBe('00:00:00')
    expect(inputs[1].element.value).toBe('')
  })

  it('selectionDuration 即時衍生（未 commit 也反映本地文字變化）', async () => {
    const w = mountParams({ start_time: '00:00:10', end_time: '00:01:00' })
    expect(w.text()).toContain('0:50')
    const endInput = w.findAll('input[type="text"]')[1]
    await endInput.setValue('00:02:00')
    // setValue 觸發 input+change；change 會 commit 並正規化，但即時 selectionDuration 應已反映輸入
    expect(w.text()).toContain('1:50')
  })
})

describe('AudioCutParams commit（本地編輯 → emit，含正規化）', () => {
  it('start 輸入框 setValue+change → emit update:params 恰一次、payload 正規化', async () => {
    const w = mountParams({ start_time: '00:01:30', end_time: '00:02:00' })
    const startInput = w.findAll('input[type="text"]')[0]
    await startInput.setValue('90')

    expect(w.emitted('update:params')).toHaveLength(1)
    expect(w.emitted('update:params')![0][0]).toEqual({
      start_time: '00:01:30', // 90 秒正規化
      end_time: '00:02:00',
    })
    // 顯示字串也正規化
    expect(startInput.element.value).toBe('00:01:30')
  })

  it('end 輸入框 setValue+change → emit payload、start 保留', async () => {
    const w = mountParams({ start_time: '00:00:10', end_time: '00:02:00' })
    const endInput = w.findAll('input[type="text"]')[1]
    await endInput.setValue('01:30')

    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toEqual({
      start_time: '00:00:10',
      end_time: '00:01:30',
    })
  })

  it('非法輸入正規化為 00:00:00', async () => {
    const w = mountParams({ start_time: '00:00:10', end_time: '00:02:00' })
    const startInput = w.findAll('input[type="text"]')[0]
    await startInput.setValue('bogus')

    expect(w.emitted('update:params')![0][0]).toEqual({
      start_time: '00:00:00',
      end_time: '00:02:00',
    })
    expect(startInput.element.value).toBe('00:00:00')
  })
})

describe('AudioCutParams 響應式衍生＋本地編輯不打斷', () => {
  it('外部替換 props.params（rerender）→ 顯示字串重推', async () => {
    const w = mountParams({ start_time: '00:01:30', end_time: '00:02:00' })
    await w.setProps({ params: { start_time: '00:00:30', end_time: '00:02:00' } })
    const inputs = w.findAll('input[type="text"]')
    expect(inputs[0].element.value).toBe('00:00:30')
  })

  it('自身 emit 回流不重推顯示字串（父層把同物件 set 回來）', async () => {
    const w = mountParams({ start_time: '00:01:30', end_time: '00:02:00' })
    const startInput = w.findAll('input[type="text"]')[0]
    await startInput.setValue('00:00:10')

    const emittedPayload = w.emitted('update:params')![0][0] as Record<string, unknown>

    // 使用者接著又打了一個非正規格式（模擬正在輸入中——只 trigger 'input'，不 commit）
    startInput.element.value = 'bogus-in-progress'
    await startInput.trigger('input')

    await w.setProps({ params: emittedPayload })

    expect(startInput.element.value).toBe('bogus-in-progress')
  })

  it('one-shot：commit 後外部改值再改回原值，顯示字串仍須正確重推（不 stale）', async () => {
    const w = mountParams({ start_time: '00:01:30', end_time: '00:02:00' })
    const startInput = w.findAll('input[type="text"]')[0]

    await startInput.setValue('00:00:10')
    expect(startInput.element.value).toBe('00:00:10')

    await w.setProps({ params: { start_time: '00:01:30', end_time: '00:02:00' } })
    expect(startInput.element.value).toBe('00:01:30')

    await w.setProps({ params: { start_time: '00:00:10', end_time: '00:02:00' } })
    expect(startInput.element.value).toBe('00:00:10')
  })
})

describe('AudioCutParams 出向：params 變 → 換算比例 → emit update:trimRange', () => {
  it('mount 時（有 duration）立即 emit 初始比例（沿舊 panel watch(duration,immediate)）', () => {
    const w = mountParams(
      { start_time: '00:00:20', end_time: '00:01:20' },
      'tool',
      { duration: 100 },
    )
    expect(w.emitted('update:trimRange')).toEqual([[{ start: 0.2, end: 0.8 }]])
  })

  it('無 fileInfo/duration → mount 不 emit', () => {
    const w = mountParams({ start_time: '00:00:20', end_time: '00:01:20' })
    expect(w.emitted('update:trimRange')).toBeUndefined()
  })

  it('外部改 params（含 duration）→ 重新換算並 emit', async () => {
    const w = mountParams({ start_time: '00:00:10', end_time: '00:00:50' }, 'tool', { duration: 100 })
    w.emitted('update:trimRange')!.length // consume baseline
    await w.setProps({ params: { start_time: '00:00:30', end_time: '00:00:90' } })
    const events = w.emitted('update:trimRange')!
    const last = events[events.length - 1][0] as { start: number; end: number }
    expect(last.start).toBeCloseTo(0.3)
    expect(last.end).toBeCloseTo(0.9)
  })

  it('end<=start → 不 emit（換算後不合法即跳過）', async () => {
    const w = mountParams({ start_time: '00:00:10', end_time: '00:00:50' }, 'tool', { duration: 100 })
    const before = w.emitted('update:trimRange')!.length
    await w.setProps({ params: { start_time: '00:00:50', end_time: '00:00:50' } })
    expect(w.emitted('update:trimRange')!.length).toBe(before)
  })
})

describe('AudioCutParams 入向：host notify(\'trimRange\', ratio) → 寫回 params', () => {
  it('notify 換算 HH:MM:SS 並 emit update:params，顯示字串同步更新', async () => {
    const w = mountParams({ start_time: '00:00:00', end_time: '00:00:00' }, 'tool', { duration: 100 })
    const before = w.emitted('update:params')?.length ?? 0

    await (w.vm as any).notify('trimRange', { start: 0.1, end: 0.9 })

    const events = w.emitted('update:params')!
    expect(events.length).toBe(before + 1)
    expect(events[events.length - 1][0]).toEqual({
      start_time: '00:00:10',
      end_time: '00:01:30',
    })

    const inputs = w.findAll('input[type="text"]')
    expect(inputs[0].element.value).toBe('00:00:10')
    expect(inputs[1].element.value).toBe('00:01:30')
  })

  it('入向後不立刻反射出向（同一 tick 內未見額外 update:trimRange）', async () => {
    const w = mountParams({ start_time: '00:00:00', end_time: '00:00:00' }, 'tool', { duration: 100 })
    const before = w.emitted('update:trimRange')?.length ?? 0

    // 尚未 await notify()（同步呼叫瞬間），旗標已壓下——這裡直接檢查呼叫後、微任務 flush 前
    const p = (w.vm as any).notify('trimRange', { start: 0.1, end: 0.9 })
    // 呼叫當下（同步階段）不應立刻新增 update:trimRange
    expect(w.emitted('update:trimRange')?.length ?? 0).toBe(before)
    await p

    // notify() resolve 後（未經 host round-trip / setProps），仍不應有新的 update:trimRange，
    // 因為出向 watcher 只在 props.params 真正變化時觸發，而本測試未呼叫 setProps。
    expect(w.emitted('update:trimRange')?.length ?? 0).toBe(before)
  })

  it('channel 非 trimRange → 忽略', async () => {
    const w = mountParams({ start_time: '00:00:00', end_time: '00:00:00' }, 'tool', { duration: 100 })
    const before = w.emitted('update:params')?.length ?? 0
    await (w.vm as any).notify('other', { start: 0.1, end: 0.9 })
    expect(w.emitted('update:params')?.length ?? 0).toBe(before)
  })

  it('無 duration → notify 忽略（無法換算）', async () => {
    const w = mountParams({ start_time: '00:00:00', end_time: '00:00:00' })
    const before = w.emitted('update:params')?.length ?? 0
    await (w.vm as any).notify('trimRange', { start: 0.1, end: 0.9 })
    expect(w.emitted('update:params')?.length ?? 0).toBe(before)
  })

  it('payload=null → 忽略', async () => {
    const w = mountParams({ start_time: '00:00:00', end_time: '00:00:00' }, 'tool', { duration: 100 })
    const before = w.emitted('update:params')?.length ?? 0
    await (w.vm as any).notify('trimRange', null)
    expect(w.emitted('update:params')?.length ?? 0).toBe(before)
  })
})

describe('AudioCutParams pipeline 語境：無 fileInfo/duration，無 trim 通道行為', () => {
  it('context=pipeline 文字欄照渲染', () => {
    const w = mountParams({ start_time: '00:00:00', end_time: '' }, 'pipeline')
    const inputs = w.findAll('input[type="text"]')
    expect(inputs).toHaveLength(2)
    expect(inputs[0].element.value).toBe('00:00:00')
  })

  it('context=pipeline 無 duration → mount 不 emit update:trimRange', () => {
    const w = mountParams({ start_time: '00:00:20', end_time: '00:01:20' }, 'pipeline')
    expect(w.emitted('update:trimRange')).toBeUndefined()
  })

  it('context=pipeline notify 仍走同一段程式碼但無 duration → 忽略', async () => {
    const w = mountParams({ start_time: '00:00:00', end_time: '' }, 'pipeline')
    const before = w.emitted('update:params')?.length ?? 0
    await (w.vm as any).notify('trimRange', { start: 0.1, end: 0.9 })
    expect(w.emitted('update:params')?.length ?? 0).toBe(before)
  })
})

describe('params/index.ts 載入表', () => {
  it('hasParamComponent("audio.cut") === true', () => {
    expect(hasParamComponent('audio.cut')).toBe(true)
  })

  it('METAS["audio.cut"].toolKey === "audio.cut"', () => {
    expect(METAS['audio.cut'].toolKey).toBe('audio.cut')
  })
})
