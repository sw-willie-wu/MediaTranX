/**
 * ImageCropParams.vue 單測（統一參數元件 spec §5；批 4 Task 4.3）。
 * 覆蓋：canvasCropRect 入向寫 params、aspect 鎖定反推、外部 setParams 更新顯示、
 * one-shot 不吞合法回寫、showCropOverlay/aspectRatio UI 便利狀態 emit（沿舊
 * ImageCropPanel 契約），仿 video/__tests__/CropParams.test.ts。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import CropParams from '../CropParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import { hasParamComponent, METAS } from '../../index'

function mockT(k: string): string {
  return k
}

function mountParams(
  params: Record<string, unknown>,
  extra: Record<string, unknown> = {},
  context: 'tool' | 'pipeline' = 'tool',
) {
  return mount(CropParams, {
    props: { params, context, fileInfo: null, ...extra },
    global: {
      mocks: { $t: mockT },
    },
  })
}

function numberInputs(w: ReturnType<typeof mountParams>) {
  return w.findAll('input[type="number"]')
}

describe('ImageCropParams 顯示', () => {
  it('mount params → 四欄位顯示 x/y/width/height', () => {
    const w = mountParams({ x: 10, y: 20, width: 300, height: 200 })
    const inputs = numberInputs(w)
    expect(inputs[0].element.value).toBe('10') // x
    expect(inputs[1].element.value).toBe('20') // y
    expect(inputs[2].element.value).toBe('300') // width
    expect(inputs[3].element.value).toBe('200') // height
  })

  it('params={}（無值）→ x/y 顯示 0、width/height 空白', () => {
    const w = mountParams({})
    const inputs = numberInputs(w)
    expect(inputs[0].element.value).toBe('0')
    expect(inputs[1].element.value).toBe('0')
    expect(inputs[2].element.value).toBe('')
    expect(inputs[3].element.value).toBe('')
  })

  it('width/height min 屬性＝1（PIL 無取偶約束，異於 video.crop 的 min=2）', () => {
    const w = mountParams({ x: 0, y: 0, width: 300, height: 200 })
    const inputs = numberInputs(w)
    expect(inputs[2].attributes('min')).toBe('1')
    expect(inputs[3].attributes('min')).toBe('1')
  })

  it('非 free 長寬比時 height input 為 disabled', async () => {
    const w = mountParams({ x: 0, y: 0, width: 100, height: 100 })
    const select = w.findComponent(AppSelect)
    select.vm.$emit('update:modelValue', '1:1')
    await w.vm.$nextTick()
    const inputs = numberInputs(w)
    expect(inputs[3].attributes('disabled')).toBeDefined()
  })

  it('free 長寬比（預設）height input 不 disabled', () => {
    const w = mountParams({ x: 0, y: 0, width: 100, height: 100 })
    const inputs = numberInputs(w)
    expect(inputs[3].attributes('disabled')).toBeUndefined()
  })
})

describe('ImageCropParams commit（欄位編輯 → emit）', () => {
  it('width 輸入框 setValue+change → emit update:params 恰一次、payload 正確（width 轉數字）', async () => {
    const w = mountParams({ x: 0, y: 0, width: 300, height: 200 })
    const widthInput = numberInputs(w)[2]
    await widthInput.setValue('640')

    expect(w.emitted('update:params')).toHaveLength(1)
    expect(w.emitted('update:params')![0][0]).toEqual({
      x: 0,
      y: 0,
      width: 640,
      height: 200,
    })
  })

  it('width 清空 → emit width:undefined（必填語意靠 host.validate 擋，非本元件）', async () => {
    const w = mountParams({ x: 0, y: 0, width: 300, height: 200 })
    const widthInput = numberInputs(w)[2]
    await widthInput.setValue('')

    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toEqual({
      x: 0,
      y: 0,
      width: undefined,
      height: 200,
    })
  })

  it('x 輸入框 change → emit payload 保留 y/width/height', async () => {
    const w = mountParams({ x: 0, y: 0, width: 300, height: 200 })
    const xInput = numberInputs(w)[0]
    await xInput.setValue('15')

    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toEqual({
      x: 15,
      y: 0,
      width: 300,
      height: 200,
    })
  })

  it('width=1（邊界值，PIL 合法）→ commit 正確', async () => {
    const w = mountParams({ x: 0, y: 0, width: 300, height: 200 })
    const widthInput = numberInputs(w)[2]
    await widthInput.setValue('1')

    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toEqual({
      x: 0,
      y: 0,
      width: 1,
      height: 200,
    })
  })
})

describe('ImageCropParams — canvasCropRect 入向', () => {
  it('canvasCropRect 變化 → 四捨五入 emit update:params（一次更新四欄位）', async () => {
    const w = mountParams({ x: 0, y: 0, width: 300, height: 200 }, { canvasCropRect: null })
    await w.setProps({ canvasCropRect: { x: 10.4, y: 20.6, w: 100.5, h: 50.2 } })

    const emitted = w.emitted('update:params')!
    expect(emitted).toHaveLength(1)
    expect(emitted[0][0]).toEqual({ x: 10, y: 21, width: 101, height: 50 })
  })

  it('canvasCropRect 寫入後顯示框同步更新（不必等 props.params 回流）', async () => {
    const w = mountParams({ x: 0, y: 0, width: 300, height: 200 }, { canvasCropRect: null })
    await w.setProps({ canvasCropRect: { x: 5, y: 5, w: 80, h: 60 } })

    const inputs = numberInputs(w)
    expect(inputs[0].element.value).toBe('5')
    expect(inputs[1].element.value).toBe('5')
    expect(inputs[2].element.value).toBe('80')
    expect(inputs[3].element.value).toBe('60')
  })

  it('canvasCropRect 為 null → 不 emit', () => {
    const w = mountParams({ x: 0, y: 0, width: 300, height: 200 }, { canvasCropRect: null })
    expect(w.emitted('update:params')).toBeUndefined()
  })
})

describe('ImageCropParams — 縱橫比鎖定反推（依 committed params.width）', () => {
  it('非 free + params.width 變化 → 依比例反推 height 並 emit', async () => {
    const w = mountParams({ x: 0, y: 0, width: 100, height: 100 })
    const select = w.findComponent(AppSelect)
    select.vm.$emit('update:modelValue', '16:9')
    await w.vm.$nextTick()

    // 選好比例後，外部（或 canvas）把 width 改成 200 → height 應反推為 200*9/16=112.5→113
    await w.setProps({ params: { x: 0, y: 0, width: 200, height: 100 } })
    await w.vm.$nextTick()

    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.height).toBe(113)

    const inputs = numberInputs(w)
    expect(inputs[3].element.value).toBe('113')
  })

  it('free 長寬比時 params.width 變化不觸發反推', async () => {
    const w = mountParams({ x: 0, y: 0, width: 100, height: 100 })
    await w.setProps({ params: { x: 0, y: 0, width: 200, height: 100 } })
    await w.vm.$nextTick()
    expect(w.emitted('update:params')).toBeUndefined()
  })
})

describe('ImageCropParams — 響應式衍生＋本地編輯不打斷（one-shot pattern）', () => {
  it('外部替換 props.params（rerender）→ 顯示重推', async () => {
    const w = mountParams({ x: 0, y: 0, width: 300, height: 200 })
    await w.setProps({ params: { x: 0, y: 0, width: 50, height: 40 } })
    const inputs = numberInputs(w)
    expect(inputs[2].element.value).toBe('50')
    expect(inputs[3].element.value).toBe('40')
  })

  it('one-shot：commit 後外部改值再改回原值，顯示仍須正確重推（不 stale）', async () => {
    const w = mountParams({ x: 0, y: 0, width: 300, height: 200 })
    const widthInput = numberInputs(w)[2]

    await widthInput.setValue('640')
    expect(widthInput.element.value).toBe('640')

    await w.setProps({ params: { x: 0, y: 0, width: 300, height: 200 } })
    expect(widthInput.element.value).toBe('300')

    // 外部又把值改回一開始 commit 的那個值（640）——one-shot lastEmitted 需已在
    // 上一次 watch 觸發時被消費清空，這次必須正常重推成 640，不被誤判成回流跳過。
    await w.setProps({ params: { x: 0, y: 0, width: 640, height: 200 } })
    expect(widthInput.element.value).toBe('640')
  })
})

describe('ImageCropParams — showCropOverlay / aspectRatio UI 便利狀態（不入 params）', () => {
  it('掛載即 emit update:showCropOverlay(true)（immediate，沿舊 panel 契約）', () => {
    const w = mountParams({ x: 0, y: 0, width: 300, height: 200 })
    expect(w.emitted('update:showCropOverlay')).toEqual([[true]])
  })

  it('選擇長寬比 → emit update:aspectRatio', async () => {
    const w = mountParams({ x: 0, y: 0, width: 300, height: 200 })
    const select = w.findComponent(AppSelect)
    select.vm.$emit('update:modelValue', '4:3')
    await w.vm.$nextTick()
    expect(w.emitted('update:aspectRatio')).toEqual([['4:3']])
  })
})

describe('ImageCropParams — maxW/maxH 依 fileInfo 夾限', () => {
  it('fileInfo 提供 width/height → max 屬性反映 fileInfo - x/y', () => {
    const w = mountParams(
      { x: 10, y: 20, width: 300, height: 200 },
      { fileInfo: { width: 1920, height: 1080 } },
    )
    const inputs = numberInputs(w)
    expect(inputs[2].attributes('max')).toBe('1910') // width max = 1920-10
    expect(inputs[3].attributes('max')).toBe('1060') // height max = 1080-20
  })

  it('fileInfo 為 null → max 落回 9999', () => {
    const w = mountParams({ x: 0, y: 0, width: 300, height: 200 })
    const inputs = numberInputs(w)
    expect(inputs[2].attributes('max')).toBe('9999')
    expect(inputs[3].attributes('max')).toBe('9999')
  })
})

describe('params/index.ts 載入表', () => {
  it('hasParamComponent("image.crop") === true', () => {
    expect(hasParamComponent('image.crop')).toBe(true)
  })

  it('METAS["image.crop"].toolKey === "image.crop"', () => {
    expect(METAS['image.crop'].toolKey).toBe('image.crop')
  })
})
