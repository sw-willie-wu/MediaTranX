/**
 * RemoveBgParams.vue 單測（統一參數元件 spec §5；批 4 Task 4.3）。
 * 覆蓋：顯示、選擇 mode 觸發 emit update:params、params/index.ts 載入表註冊。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import RemoveBgParams from '../RemoveBgParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import { hasParamComponent, METAS } from '../../index'

function mockT(k: string): string {
  return k
}

function mountParams(params: Record<string, unknown>, context: 'tool' | 'pipeline' = 'tool') {
  return mount(RemoveBgParams, {
    props: { params, context, fileInfo: null },
    global: {
      mocks: { $t: mockT },
    },
  })
}

describe('RemoveBgParams 顯示', () => {
  it('mount params={mode:"person"} → AppSelect modelValue 為 person', () => {
    const w = mountParams({ mode: 'person' })
    const select = w.findComponent(AppSelect)
    expect(select.props('modelValue')).toBe('person')
  })

  it('params.mode 非字串（缺值）→ 落回 auto', () => {
    const w = mountParams({})
    const select = w.findComponent(AppSelect)
    expect(select.props('modelValue')).toBe('auto')
  })

  it('options 集合＝auto/person/product/animal/anime（沿舊 panel）', () => {
    const w = mountParams({ mode: 'auto' })
    const select = w.findComponent(AppSelect)
    const opts = (select.props('options') as Array<{ value: string }>).map((o) => o.value)
    expect(opts).toEqual(['auto', 'person', 'product', 'animal', 'anime'])
  })
})

describe('RemoveBgParams commit（選擇 → emit）', () => {
  it('選擇 mode → emit update:params 恰含新 mode', async () => {
    const w = mountParams({ mode: 'auto' })
    const select = w.findComponent(AppSelect)
    select.vm.$emit('update:modelValue', 'anime')
    await w.vm.$nextTick()

    expect(w.emitted('update:params')).toEqual([[{ mode: 'anime' }]])
  })

  it('選擇 mode → 保留 params 其他既有鍵（雖 schema 只有 mode，驗證 spread 語意）', async () => {
    const w = mountParams({ mode: 'auto', extra: 'kept' })
    const select = w.findComponent(AppSelect)
    select.vm.$emit('update:modelValue', 'product')
    await w.vm.$nextTick()

    expect(w.emitted('update:params')![0][0]).toEqual({ mode: 'product', extra: 'kept' })
  })
})

describe('params/index.ts 載入表', () => {
  it('hasParamComponent("image.remove_bg") === true', () => {
    expect(hasParamComponent('image.remove_bg')).toBe(true)
  })

  it('METAS["image.remove_bg"].toolKey === "image.remove_bg"', () => {
    expect(METAS['image.remove_bg'].toolKey).toBe('image.remove_bg')
  })
})
