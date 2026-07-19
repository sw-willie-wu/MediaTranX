/**
 * useKeyHeld 泛化核心＋useSpaceHeld/useShiftHeld 包裝——2026-07-16 畫布 UX
 * 批次 Task 5。useSpaceHeld 原無測試，泛化時一併補核心行為回歸。
 */
import { describe, it, expect, afterEach } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'
import { useKeyHeld, useShiftHeld } from '../useKeyHeld'
import { useSpaceHeld } from '../useSpaceHeld'

let wrapper: VueWrapper | null = null
afterEach(() => { wrapper?.unmount(); wrapper = null })

function mountWith<T>(setup: () => T): T {
  let out!: T
  const Comp = defineComponent({
    setup() { out = setup(); return () => h('div') },
  })
  wrapper = mount(Comp, { attachTo: document.body })
  return out
}

function key(type: 'keydown' | 'keyup', init: KeyboardEventInit, target?: HTMLElement) {
  const e = new KeyboardEvent(type, { bubbles: true, cancelable: true, ...init })
  ;(target ?? window).dispatchEvent(e)
  return e
}

describe('useKeyHeld / useShiftHeld / useSpaceHeld', () => {
  it('keydown 設 held、keyup 清除；非目標鍵不影響', () => {
    const { isShiftHeld } = mountWith(() => useShiftHeld())
    expect(isShiftHeld.value).toBe(false)
    key('keydown', { key: 'Shift' })
    expect(isShiftHeld.value).toBe(true)
    key('keydown', { key: 'a' })
    key('keyup', { key: 'a' })
    expect(isShiftHeld.value).toBe(true)
    key('keyup', { key: 'Shift' })
    expect(isShiftHeld.value).toBe(false)
  })

  it('e.repeat 跳過（不重設狀態）', () => {
    const { isHeld } = mountWith(() => useKeyHeld({ match: (e) => e.key === 'x' }))
    key('keydown', { key: 'x', repeat: true })
    expect(isHeld.value).toBe(false)             // repeat 不觸發初次按住
    key('keydown', { key: 'x' })
    expect(isHeld.value).toBe(true)
  })

  it('window blur 重置（Alt-Tab 不卡按住）', () => {
    const { isShiftHeld } = mountWith(() => useShiftHeld())
    key('keydown', { key: 'Shift' })
    expect(isShiftHeld.value).toBe(true)
    window.dispatchEvent(new Event('blur'))
    expect(isShiftHeld.value).toBe(false)
  })

  it('useSpaceHeld：焦點在輸入框時不搶、不 preventDefault（本職保留）', () => {
    const { isSpaceHeld } = mountWith(() => useSpaceHeld())
    const input = document.createElement('input')
    document.body.appendChild(input)
    const e = key('keydown', { code: 'Space' }, input)
    expect(isSpaceHeld.value).toBe(false)
    expect(e.defaultPrevented).toBe(false)
    input.remove()
  })

  it('useSpaceHeld：畫布焦點按 Space → held＋preventDefault（防捲動）', () => {
    const { isSpaceHeld } = mountWith(() => useSpaceHeld())
    const e = key('keydown', { code: 'Space' })
    expect(isSpaceHeld.value).toBe(true)
    expect(e.defaultPrevented).toBe(true)
    key('keyup', { code: 'Space' })
    expect(isSpaceHeld.value).toBe(false)
  })

  it('useShiftHeld：輸入框內按 Shift 也追蹤（不 skipInteractive）、不 preventDefault', () => {
    const { isShiftHeld } = mountWith(() => useShiftHeld())
    const input = document.createElement('input')
    document.body.appendChild(input)
    const e = key('keydown', { key: 'Shift' }, input)
    expect(isShiftHeld.value).toBe(true)
    expect(e.defaultPrevented).toBe(false)
    key('keyup', { key: 'Shift' })
    input.remove()
  })

  it('unmount 後不再監聽', () => {
    const { isShiftHeld } = mountWith(() => useShiftHeld())
    wrapper!.unmount()
    wrapper = null
    key('keydown', { key: 'Shift' })
    expect(isShiftHeld.value).toBe(false)
  })
})
