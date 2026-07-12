import { describe, it, expect } from 'vitest'
import { normalizeParams } from '../recipe'
import type { ToolSpec } from '../types'

// 測試用迷你 registry（不依賴真 registry，規則測試與抄寫進度解耦）
const REG: Record<string, ToolSpec> = {
  'x.dict': {
    toolKey: 'x.dict', apiPath: '/x/dict', labelKey: 'x', kind: 'tool',
    inputKinds: ['video'],
    outputKind: () => 'video',
    paramSchema: [{ name: 'opts', type: 'dict', default: {} }],
  },
  'x.list': {
    toolKey: 'x.list', apiPath: '/x/list', labelKey: 'x', kind: 'tool',
    inputKinds: ['video'],
    outputKind: () => 'video',
    paramSchema: [{ name: 'items', type: 'list', default: [] }],
  },
  'x.listStr': {
    toolKey: 'x.listStr', apiPath: '/x/listStr', labelKey: 'x', kind: 'tool',
    inputKinds: ['video'],
    outputKind: () => 'video',
    paramSchema: [{ name: 'items', type: 'list', itemType: 'string', default: [] }],
  },
  'x.enumNumber': {
    toolKey: 'x.enumNumber', apiPath: '/x/enumNumber', labelKey: 'x', kind: 'tool',
    inputKinds: ['video'],
    outputKind: () => 'video',
    paramSchema: [
      { name: 'mode', type: 'enum', options: ['a', 'b'], default: 'a' },
      { name: 'fps', type: 'number', min: 1, max: 60, default: 12 },
    ],
  },
}

describe('normalizeParams — dict field', () => {
  it('accepts a plain object', () => {
    const { params, issues } = normalizeParams({ opts: { a: 1 } }, REG['x.dict'])
    expect(params).toEqual({ opts: { a: 1 } })
    expect(issues).toEqual([])
  })

  it('rejects array', () => {
    const { issues } = normalizeParams({ opts: [1, 2] }, REG['x.dict'])
    expect(issues.map(i => i.code)).toContain('param_invalid')
  })

  it('rejects null', () => {
    const { issues } = normalizeParams({ opts: null }, REG['x.dict'])
    expect(issues.map(i => i.code)).toContain('param_invalid')
  })

  it('rejects string', () => {
    const { issues } = normalizeParams({ opts: 'nope' }, REG['x.dict'])
    expect(issues.map(i => i.code)).toContain('param_invalid')
  })
})

describe('normalizeParams — list field', () => {
  it('accepts an array', () => {
    const { params, issues } = normalizeParams({ items: [1, 2, 3] }, REG['x.list'])
    expect(params).toEqual({ items: [1, 2, 3] })
    expect(issues).toEqual([])
  })

  it('rejects non-array', () => {
    const { issues } = normalizeParams({ items: { a: 1 } }, REG['x.list'])
    expect(issues.map(i => i.code)).toContain('param_invalid')
  })

  it('rejects array with wrong itemType (string expected)', () => {
    const { issues } = normalizeParams({ items: ['a', 1] }, REG['x.listStr'])
    expect(issues.map(i => i.code)).toContain('param_invalid')
  })

  it('accepts array matching itemType (string)', () => {
    const { params, issues } = normalizeParams({ items: ['a', 'b'] }, REG['x.listStr'])
    expect(params).toEqual({ items: ['a', 'b'] })
    expect(issues).toEqual([])
  })
})

describe('normalizeParams — existing field types no regression', () => {
  it('rejects illegal enum value', () => {
    const { issues } = normalizeParams({ mode: 'c' }, REG['x.enumNumber'])
    expect(issues.map(i => i.code)).toContain('param_invalid')
  })

  it('coerces number string to number', () => {
    const { params, issues } = normalizeParams({ fps: '24' }, REG['x.enumNumber'])
    expect(params.fps).toBe(24)
    expect(issues).toEqual([])
  })
})
