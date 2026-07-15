/**
 * 畫布鍵盤快捷鍵判定純函式（spec F2/F3）——matchShortcut 矩陣、
 * pickConnectPair 方向判定、isEditableTarget。
 */
import { describe, it, expect } from 'vitest'
import { isEditableTarget, matchShortcut, pickConnectPair } from '../canvasKeys'

const ev = (init: KeyboardEventInit) => new KeyboardEvent('keydown', init)

describe('matchShortcut', () => {
  it('C（無修飾鍵）→ connect；帶修飾鍵的 C 不觸發 connect', () => {
    expect(matchShortcut(ev({ key: 'c' }))).toBe('connect')
    expect(matchShortcut(ev({ key: 'C' }))).toBe('connect')
    expect(matchShortcut(ev({ key: 'c', shiftKey: true }))).toBeNull()
    expect(matchShortcut(ev({ key: 'c', altKey: true }))).toBeNull()
  })

  it('Ctrl+Z → undo；Ctrl+Shift+Z / Ctrl+Y → redo；Cmd 同 Ctrl', () => {
    expect(matchShortcut(ev({ key: 'z', ctrlKey: true }))).toBe('undo')
    expect(matchShortcut(ev({ key: 'z', ctrlKey: true, shiftKey: true }))).toBe('redo')
    expect(matchShortcut(ev({ key: 'y', ctrlKey: true }))).toBe('redo')
    expect(matchShortcut(ev({ key: 'z', metaKey: true }))).toBe('undo')
  })

  it('Ctrl+C → copy；Ctrl+V → paste；Alt 組合不觸發', () => {
    expect(matchShortcut(ev({ key: 'c', ctrlKey: true }))).toBe('copy')
    expect(matchShortcut(ev({ key: 'v', ctrlKey: true }))).toBe('paste')
    expect(matchShortcut(ev({ key: 'z', ctrlKey: true, altKey: true }))).toBeNull()
    expect(matchShortcut(ev({ key: 'x', ctrlKey: true }))).toBeNull()
  })
})

describe('isEditableTarget', () => {
  it('input/textarea/contenteditable → true；一般元素 → false', () => {
    const input = document.createElement('input')
    document.body.appendChild(input)
    const div = document.createElement('div')
    document.body.appendChild(div)
    const ce = document.createElement('div')
    ce.setAttribute('contenteditable', 'true')
    document.body.appendChild(ce)
    const at = (t: HTMLElement) => {
      let captured: KeyboardEvent | null = null
      t.addEventListener('keydown', (e) => { captured = e as KeyboardEvent }, { once: true })
      t.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', bubbles: true }))
      return isEditableTarget(captured!)
    }
    expect(at(input)).toBe(true)
    expect(at(ce)).toBe(true)
    expect(at(div)).toBe(false)
    input.remove(); div.remove(); ce.remove()
  })
})

describe('pickConnectPair', () => {
  const n = (id: string, x: number, y = 0) => ({ id, x, y })

  it('選取數 ≠ 2 → null', () => {
    expect(pickConnectPair([n('a', 0)], () => null)).toBeNull()
    expect(pickConnectPair([n('a', 0), n('b', 1), n('c', 2)], () => null)).toBeNull()
  })

  it('左→右合法即用（含 root→tool）', () => {
    const calls: string[] = []
    const r = pickConnectPair([n('tool', 200), n('root', 0)], (f, t) => { calls.push(`${f}>${t}`); return null })
    expect(r).toEqual({ from: 'root', to: 'tool' })
    expect(calls).toEqual(['root>tool'])
  })

  it('左→右失敗試右→左', () => {
    const r = pickConnectPair([n('a', 0), n('b', 100)],
      (f) => (f === 'a' ? 'nope' : null))
    expect(r).toEqual({ from: 'b', to: 'a' })
  })

  it('兩向皆失敗 → 回第一次嘗試的錯誤', () => {
    const r = pickConnectPair([n('a', 0), n('b', 100)], (f) => `err-${f}`)
    expect(r).toEqual({ error: 'err-a' })
  })

  it('x 相同以 y、再以 id tie-break（穩定）', () => {
    const r1 = pickConnectPair([n('b', 50, 10), n('a', 50, 0)], () => null)
    expect(r1).toEqual({ from: 'a', to: 'b' })      // y 小者為左
    const r2 = pickConnectPair([n('b', 50, 10), n('a', 50, 10)], () => null)
    expect(r2).toEqual({ from: 'a', to: 'b' })      // id 序
  })
})
