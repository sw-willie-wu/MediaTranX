/**
 * ConvertParams.vue 單測（統一參數元件 spec §5；批 4 Task 4.1）。
 * 覆蓋：resizeMode 三態響應式衍生（one-shot pattern）、scale %↔比值轉換、quality/coalesce
 * 條件顯示、output_format 切換 commit。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import ConvertParams from '../ConvertParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'
import AppToggle from '@/components/common/AppToggle.vue'

function mockT(k: string): string {
  return k
}

function mountParams(params: Record<string, unknown>, fileInfo: Record<string, unknown> | null = null) {
  return mount(ConvertParams, {
    props: { params, context: 'tool', fileInfo },
    global: { mocks: { $t: mockT } },
  })
}

describe('ConvertParams — resizeMode 三態響應式衍生', () => {
  it('params={scale:1.5} → resizeMode=scale，顯示 150%', () => {
    const w = mountParams({ output_format: 'png', scale: 1.5 })
    expect(w.text()).toContain('150')
    expect(w.find('.size-inputs').exists()).toBe(false)
  })

  it('params={width:800,height:600} → resizeMode=custom，寬高欄顯示 800/600', () => {
    const w = mountParams({ output_format: 'png', width: 800, height: 600 })
    const inputs = w.findAll('.size-inputs input[type="number"]')
    expect(inputs[0].element.value).toBe('800')
    expect(inputs[1].element.value).toBe('600')
  })

  it('params 無 scale/width/height → resizeMode=original，無縮放/自訂區塊', () => {
    const w = mountParams({ output_format: 'png' })
    expect(w.find('.size-inputs').exists()).toBe(false)
  })

  it('外部 setProps 切到 custom → 響應式重推（one-shot：非回流）', async () => {
    const w = mountParams({ output_format: 'png', scale: 1.5 })
    await w.setProps({ params: { output_format: 'png', width: 400, height: 300 } })
    const inputs = w.findAll('.size-inputs input[type="number"]')
    expect(inputs[0].element.value).toBe('400')
    expect(inputs[1].element.value).toBe('300')
  })
})

describe('ConvertParams — scale % ↔ 比值轉換', () => {
  it('選 scale 模式 → commit scale=1.0（100%）、width/height 清空', async () => {
    const w = mountParams({ output_format: 'png', width: 800, height: 600 })
    const modeSelect = w.findAllComponents(AppSelect).find((s) => s.props('modelValue') === 'custom')!
    modeSelect.vm.$emit('update:modelValue', 'scale')
    await w.vm.$nextTick()
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.scale).toBe(1)
    expect(last.width).toBeUndefined()
    expect(last.height).toBeUndefined()
  })

  it('scale 模式下拖動滑桿至 150% → emit scale=1.5', async () => {
    const w = mountParams({ output_format: 'png', scale: 1.0 })
    const range = w.findComponent(AppRange)
    range.vm.$emit('update:modelValue', 150)
    await w.vm.$nextTick()
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.scale).toBe(1.5)
  })

  it('選 custom 模式 → commit scale=undefined', async () => {
    const w = mountParams({ output_format: 'png', scale: 1.5 })
    const modeSelect = w.findAllComponents(AppSelect).find((s) => s.props('modelValue') === 'scale')!
    modeSelect.vm.$emit('update:modelValue', 'custom')
    await w.vm.$nextTick()
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.scale).toBeUndefined()
  })

  it('選 original 模式 → commit scale/width/height 全 undefined', async () => {
    const w = mountParams({ output_format: 'png', width: 800, height: 600 })
    const modeSelect = w.findAllComponents(AppSelect).find((s) => s.props('modelValue') === 'custom')!
    modeSelect.vm.$emit('update:modelValue', 'original')
    await w.vm.$nextTick()
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.scale).toBeUndefined()
    expect(last.width).toBeUndefined()
    expect(last.height).toBeUndefined()
  })
})

describe('ConvertParams — quality/coalesce 條件顯示（依 output_format）', () => {
  it('jpg → 顯示 quality 進階區', () => {
    const w = mountParams({ output_format: 'jpg' })
    expect(w.findComponent(AppRange).exists()).toBe(true)
  })

  it('png → 不顯示 quality 進階區', () => {
    const w = mountParams({ output_format: 'png' })
    expect(w.findComponent(AppRange).exists()).toBe(false)
  })

  it('gif → 顯示 coalesce toggle', () => {
    const w = mountParams({ output_format: 'gif' })
    expect(w.findComponent(AppToggle).exists()).toBe(true)
  })

  it('png → 不顯示 coalesce toggle', () => {
    const w = mountParams({ output_format: 'png' })
    expect(w.findComponent(AppToggle).exists()).toBe(false)
  })
})

describe('ConvertParams — output_format 切換 commit', () => {
  it('切到 webp → emit update:params { output_format: "webp" }（其餘欄位保留）', async () => {
    const w = mountParams({ output_format: 'png', width: 800 })
    const formatSelect = w.findAllComponents(AppSelect)[0]
    formatSelect.vm.$emit('update:modelValue', 'webp')
    await w.vm.$nextTick()
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.output_format).toBe('webp')
    expect(last.width).toBe(800)
  })
})

describe('ConvertParams — 縮放尺寸提示（依 fileInfo）', () => {
  it('fileInfo 提供 width/height → scale 模式顯示換算後尺寸', () => {
    const w = mountParams({ output_format: 'png', scale: 0.5 }, { width: 1000, height: 500 })
    expect(w.text()).toContain('1000')
    expect(w.text()).toContain('500')
  })
})
