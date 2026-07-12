/**
 * FilterParams.vue 單測（統一參數元件 spec §5；批 4 Task 4.2 ⭐合併 task）。
 * 覆蓋：fieldGroup 分組渲染（adjust/filter/未傳全集）、UI↔後端尺度逐欄轉換、reset 只重置
 * 自己 fieldGroup 的欄位、preview-change 形狀（自己組實際值＋另一組中性值）。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import FilterParams from '../FilterParams.vue'
import AppRange from '@/components/common/AppRange.vue'

function mockT(k: string): string {
  return k
}

function mountParams(
  params: Record<string, unknown>,
  fieldGroup?: 'adjust' | 'filter',
) {
  return mount(FilterParams, {
    props: { params, context: 'tool', fileInfo: null, ...(fieldGroup ? { fieldGroup } : {}) },
    global: { mocks: { $t: mockT } },
  })
}

const ADJUST_DEFAULTS = { brightness: 1, contrast: 1, saturation: 1, hue: 0, sharpness: 1, warmth: 0 }
const FILTER_DEFAULTS = { grayscale: 0, sepia: 0, invert: 0, blur: 0, vignette: 0 }
const ALL_DEFAULTS = { ...ADJUST_DEFAULTS, ...FILTER_DEFAULTS }

describe('FilterParams — fieldGroup 分組渲染', () => {
  it('fieldGroup=adjust → 只顯示 6 個 adjust 滑桿，無 filter 標題', () => {
    const w = mountParams(ALL_DEFAULTS, 'adjust')
    expect(w.findAllComponents(AppRange)).toHaveLength(6)
    expect(w.text()).toContain('image.adjust.title')
    expect(w.text()).not.toContain('image.filter.title')
  })

  it('fieldGroup=filter → 只顯示 5 個 filter 滑桿，無 adjust 標題', () => {
    const w = mountParams(ALL_DEFAULTS, 'filter')
    expect(w.findAllComponents(AppRange)).toHaveLength(5)
    expect(w.text()).toContain('image.filter.title')
    expect(w.text()).not.toContain('image.adjust.title')
  })

  it('未傳 fieldGroup（pipeline 全集）→ 兩組皆顯示，共 11 個滑桿', () => {
    const w = mountParams(ALL_DEFAULTS)
    expect(w.findAllComponents(AppRange)).toHaveLength(11)
    expect(w.text()).toContain('image.adjust.title')
    expect(w.text()).toContain('image.filter.title')
  })
})

describe('FilterParams — UI↔後端尺度轉換（顯示值）', () => {
  it('brightness/contrast/saturation/sharpness：後端 1.5 → 顯示 150%', () => {
    const w = mountParams({ ...ALL_DEFAULTS, brightness: 1.5, contrast: 0.5, saturation: 2.0, sharpness: 1.2 })
    expect(w.text()).toContain('150%')
    expect(w.text()).toContain('50%')
    expect(w.text()).toContain('200%')
    expect(w.text()).toContain('120%')
  })

  it('hue：後端 -45 → 顯示 -45°（原值直傳，無尺度轉換）', () => {
    const w = mountParams({ ...ALL_DEFAULTS, hue: -45 })
    expect(w.text()).toContain('-45°')
  })

  it('warmth：後端 0.5 → 顯示「暖 +50」', () => {
    const w = mountParams({ ...ALL_DEFAULTS, warmth: 0.5 })
    expect(w.text()).toContain('image.adjust.warm +50')
  })

  it('grayscale/sepia/invert/vignette：後端 0.3 → 顯示 30%', () => {
    const w = mountParams({ ...ALL_DEFAULTS, grayscale: 0.3, sepia: 0.4, invert: 0.6, vignette: 0.8 }, 'filter')
    expect(w.text()).toContain('30%')
    expect(w.text()).toContain('40%')
    expect(w.text()).toContain('60%')
    expect(w.text()).toContain('80%')
  })

  it('blur：後端 7 → 顯示 7px（直傳，無尺度轉換）', () => {
    const w = mountParams({ ...ALL_DEFAULTS, blur: 7 }, 'filter')
    expect(w.text()).toContain('7px')
  })
})

describe('FilterParams — 滑桿拖動 commit（UI → 後端尺度）', () => {
  it('brightness 滑桿拖到 200 → emit brightness=2（/100）', async () => {
    const w = mountParams(ALL_DEFAULTS, 'adjust')
    const range = w.findAllComponents(AppRange)[0] // brightness 是第一個
    range.vm.$emit('update:modelValue', 200)
    await w.vm.$nextTick()
    const last = lastEmitted(w)
    expect(last.brightness).toBe(2)
  })

  it('hue 滑桿拖到 -90 → emit hue=-90（原值直傳）', async () => {
    const w = mountParams(ALL_DEFAULTS, 'adjust')
    // template 順序：brightness/contrast/saturation/sharpness/hue/warmth → hue 是 index 4
    const hueRange = w.findAllComponents(AppRange)[4]
    hueRange.vm.$emit('update:modelValue', -90)
    await w.vm.$nextTick()
    const last = lastEmitted(w)
    expect(last.hue).toBe(-90)
  })

  it('warmth 滑桿拖到 -50 → emit warmth=-0.5（/100）', async () => {
    const w = mountParams(ALL_DEFAULTS, 'adjust')
    const warmthRange = w.findAllComponents(AppRange)[5]
    warmthRange.vm.$emit('update:modelValue', -50)
    await w.vm.$nextTick()
    const last = lastEmitted(w)
    expect(last.warmth).toBe(-0.5)
  })

  it('blur 滑桿拖到 15 → emit blur=15（直傳）', async () => {
    const w = mountParams(ALL_DEFAULTS, 'filter')
    const blurRange = w.findAllComponents(AppRange)[3] // grayscale/sepia/invert/blur/vignette
    blurRange.vm.$emit('update:modelValue', 15)
    await w.vm.$nextTick()
    const last = lastEmitted(w)
    expect(last.blur).toBe(15)
  })

  it('grayscale 滑桿拖到 60 → emit grayscale=0.6（/100）', async () => {
    const w = mountParams(ALL_DEFAULTS, 'filter')
    const grayscaleRange = w.findAllComponents(AppRange)[0]
    grayscaleRange.vm.$emit('update:modelValue', 60)
    await w.vm.$nextTick()
    const last = lastEmitted(w)
    expect(last.grayscale).toBe(0.6)
  })
})

describe('FilterParams — reset 只重置自己 fieldGroup 的欄位', () => {
  it('fieldGroup=adjust：reset 按鈕只重置 6 個 adjust 欄位為中性值，filter 半保留原值', async () => {
    const params = { ...ALL_DEFAULTS, brightness: 2.5, hue: 90, grayscale: 0.9, blur: 12 }
    const w = mountParams(params, 'adjust')
    const btn = w.find('button.btn-secondary')
    await btn.trigger('click')
    const last = lastEmitted(w)
    expect(last).toMatchObject(ADJUST_DEFAULTS)
    // filter 半（非自己組）保留原值，未被 reset 觸碰
    expect(last.grayscale).toBe(0.9)
    expect(last.blur).toBe(12)
  })

  it('fieldGroup=filter：reset 按鈕只重置 5 個 filter 欄位為中性值，adjust 半保留原值', async () => {
    const params = { ...ALL_DEFAULTS, brightness: 2.5, grayscale: 0.9, blur: 12 }
    const w = mountParams(params, 'filter')
    const btn = w.find('button.btn-secondary')
    await btn.trigger('click')
    const last = lastEmitted(w)
    expect(last).toMatchObject(FILTER_DEFAULTS)
    expect(last.brightness).toBe(2.5) // adjust 半保留
  })
})

describe('FilterParams — preview-change 形狀（自己組實際值＋另一組中性值）', () => {
  it('fieldGroup=adjust：preview 讀 adjust 實際值，filter 半強制中性值（即使 params 裡有非中性殘值）', () => {
    const params = { ...ALL_DEFAULTS, brightness: 1.8, hue: 30, grayscale: 0.9, blur: 15 }
    const w = mountParams(params, 'adjust')
    const events = w.emitted('preview-change')!
    const last = events[events.length - 1][0] as Record<string, unknown>
    expect(last.brightness).toBe(1.8)
    expect(last.hue).toBe(30)
    // 非自己組欄位強制中性值，不讀 props.params 裡的殘值
    expect(last.grayscale).toBe(0)
    expect(last.blur).toBe(0)
  })

  it('fieldGroup=filter：preview 讀 filter 實際值，adjust 半強制中性值', () => {
    const params = { ...ALL_DEFAULTS, brightness: 1.8, grayscale: 0.9, blur: 15 }
    const w = mountParams(params, 'filter')
    const events = w.emitted('preview-change')!
    const last = events[events.length - 1][0] as Record<string, unknown>
    expect(last.grayscale).toBe(0.9)
    expect(last.blur).toBe(15)
    expect(last.brightness).toBe(1) // 中性值，非 1.8
  })

  it('未傳 fieldGroup（全集）：preview 兩組皆讀實際值，無中性替代', () => {
    const params = { ...ALL_DEFAULTS, brightness: 1.8, grayscale: 0.9 }
    const w = mountParams(params)
    const events = w.emitted('preview-change')!
    const last = events[events.length - 1][0] as Record<string, unknown>
    expect(last.brightness).toBe(1.8)
    expect(last.grayscale).toBe(0.9)
  })

  it('mount 時立即 emit 一次（immediate:true，供 WebGL 預覽初始渲染）', () => {
    const w = mountParams(ALL_DEFAULTS, 'adjust')
    expect(w.emitted('preview-change')).toBeTruthy()
    expect(w.emitted('preview-change')!.length).toBeGreaterThanOrEqual(1)
  })
})

function lastEmitted(w: ReturnType<typeof mountParams>): Record<string, unknown> {
  const emitted = w.emitted('update:params')!
  return emitted[emitted.length - 1][0] as Record<string, unknown>
}
