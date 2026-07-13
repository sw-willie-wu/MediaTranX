/**
 * AiRemoveParams.vue 單測（統一參數元件 spec §5；批 4 Task 4.5 Part C——最小侵入拆分）。
 * 覆蓋：工具列選擇（4 模式）v-model 雙向、brush/eraser 顯示 slider（polygon/bezier 顯示
 * hint 文字取代）、brushSize v-model 雙向、清除鈕 disabled 透傳與 emit clearMask。
 *
 * 本元件不進 PARAM_COMPONENTS/METAS/registry（無 meta.ts）——見 ImageAiRemovePanel.vue
 * 掛載處與 batch4-recon.md §7 remove_object 邊界記錄；mask_data 仍完全由 canvas/panel
 * 管理，本元件只負責 brushSize/toolMode 兩個互動狀態的受控 UI。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import AiRemoveParams from '../AiRemoveParams.vue'
import AppRange from '@/components/common/AppRange.vue'

function mountParams(props: { brushSize?: number; toolMode?: string; isDisabled?: boolean } = {}) {
  return mount(AiRemoveParams, {
    props: {
      brushSize: props.brushSize ?? 20,
      toolMode: props.toolMode ?? 'brush',
      isDisabled: props.isDisabled ?? false,
    },
    global: { mocks: { $t: (k: string) => k } },
  })
}

describe('AiRemoveParams — 工具列（4 模式）', () => {
  it('渲染 4 個工具按鈕（brush/polygon/bezier/eraser）', () => {
    const w = mountParams()
    const btns = w.findAll('.mask-tool-btn')
    expect(btns).toHaveLength(4)
  })

  it('toolMode="polygon" → 對應按鈕帶 is-active class', () => {
    const w = mountParams({ toolMode: 'polygon' })
    const btns = w.findAll('.mask-tool-btn')
    // 第二個按鈕＝polygon（沿舊 panel tools 陣列順序 brush/polygon/bezier/eraser）
    expect(btns[1].classes()).toContain('is-active')
    expect(btns[0].classes()).not.toContain('is-active')
  })

  it('點擊工具按鈕 → emit update:toolMode 帶對應模式', async () => {
    const w = mountParams({ toolMode: 'brush' })
    const btns = w.findAll('.mask-tool-btn')
    await btns[2].trigger('click') // bezier
    expect(w.emitted('update:toolMode')).toEqual([['bezier']])
  })
})

describe('AiRemoveParams — brush/eraser slider vs polygon/bezier hint', () => {
  it('toolMode="brush" → 渲染 AppRange（brushSize slider）', () => {
    const w = mountParams({ toolMode: 'brush' })
    expect(w.findComponent(AppRange).exists()).toBe(true)
  })

  it('toolMode="eraser" → 渲染 AppRange', () => {
    const w = mountParams({ toolMode: 'eraser' })
    expect(w.findComponent(AppRange).exists()).toBe(true)
  })

  it('toolMode="polygon" → 不渲染 AppRange，改渲染 polygon_hint 文字', () => {
    const w = mountParams({ toolMode: 'polygon' })
    expect(w.findComponent(AppRange).exists()).toBe(false)
    expect(w.text()).toContain('image.remove_object.polygon_hint')
  })

  it('toolMode="bezier" → 不渲染 AppRange', () => {
    const w = mountParams({ toolMode: 'bezier' })
    expect(w.findComponent(AppRange).exists()).toBe(false)
  })
})

describe('AiRemoveParams — brushSize v-model 雙向', () => {
  it('AppRange modelValue = props.brushSize', () => {
    const w = mountParams({ brushSize: 35, toolMode: 'brush' })
    expect(w.findComponent(AppRange).props('modelValue')).toBe(35)
  })

  it('AppRange 更新 → emit update:brushSize', async () => {
    const w = mountParams({ toolMode: 'brush' })
    const range = w.findComponent(AppRange)
    range.vm.$emit('update:modelValue', 50)
    await w.vm.$nextTick()
    expect(w.emitted('update:brushSize')).toEqual([[50]])
  })
})

describe('AiRemoveParams — 清除鈕', () => {
  it('isDisabled=false → 清除鈕未 disabled', () => {
    const w = mountParams({ isDisabled: false })
    const btn = w.find('button.btn-secondary')
    expect(btn.attributes('disabled')).toBeUndefined()
  })

  it('isDisabled=true → 清除鈕 disabled', () => {
    const w = mountParams({ isDisabled: true })
    const btn = w.find('button.btn-secondary')
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('點擊清除鈕 → emit clearMask', async () => {
    const w = mountParams({ isDisabled: false })
    await w.find('button.btn-secondary').trigger('click')
    expect(w.emitted('clearMask')).toBeTruthy()
  })
})
