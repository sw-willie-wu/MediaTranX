/**
 * 畫布視覺判定純函式（spec F4-①/②）——issue bar 三態與節點紅框謂詞。
 */
import { describe, it, expect } from 'vitest'
import { barState, nodeFlagged } from '../viewState'
import type { ValidationIssue } from '../types'

const err = (nodeId: string, code: ValidationIssue['code'] = 'param_invalid'): ValidationIssue =>
  ({ severity: 'error', nodeId, code, message: `err ${nodeId}` })
const warn = (nodeId: string, code: ValidationIssue['code']): ValidationIssue =>
  ({ severity: 'warning', nodeId, code, message: `warn ${nodeId}` })

describe('nodeFlagged（紅框謂詞）', () => {
  it('error 級 issue → 紅框；tool_unrooted warning → 紅框（拆碼零回退）', () => {
    const issues = [err('a'), warn('x', 'tool_unrooted')]
    expect(nodeFlagged('a', issues)).toBe(true)
    expect(nodeFlagged('x', issues)).toBe(true)
  })

  it('orphan_node/param_unknown 等其他 warning 不紅（維持現狀）', () => {
    const issues = [warn('lone', 'orphan_node'), warn('b', 'param_unknown')]
    expect(nodeFlagged('lone', issues)).toBe(false)
    expect(nodeFlagged('b', issues)).toBe(false)
  })

  it('model_missing（error）紅框；無 issue 節點不紅', () => {
    const issues: ValidationIssue[] = [{ severity: 'error', nodeId: 'm', code: 'model_missing', message: 'x' }]
    expect(nodeFlagged('m', issues)).toBe(true)
    expect(nodeFlagged('clean', issues)).toBe(false)
  })
})

describe('barState（issue bar 三態）', () => {
  it('blocking 存在 → danger、首條＝blocking[0]、+N 含三組', () => {
    const s = barState([err('a')], [err('x'), err('y')], [err('m', 'model_missing')])!
    expect(s.tone).toBe('danger')
    expect(s.message).toBe('err a')
    expect(s.extra).toBe(3)    // (1 blocking + 1 model + 2 advisory) - 1
  })

  it('只有 modelIssues → danger、首條＝model[0]', () => {
    const s = barState([], [], [err('m', 'model_missing')])!
    expect(s.tone).toBe('danger')
    expect(s.message).toBe('err m')
    expect(s.extra).toBe(0)
  })

  it('僅 advisory → warning、+N＝advisory−1', () => {
    const s = barState([], [err('x'), err('y')], [])!
    expect(s.tone).toBe('warning')
    expect(s.message).toBe('err x')
    expect(s.extra).toBe(1)
  })

  it('全空 → null（乾淨懸空鏈的 warning 不觸發 bar）', () => {
    expect(barState([], [], [])).toBeNull()
  })
})
