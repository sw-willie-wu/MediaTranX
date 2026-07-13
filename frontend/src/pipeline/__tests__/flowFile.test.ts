import { describe, expect, it } from 'vitest'
import { FLOW_FORMAT, isFlowFileName, parseFlow, serializeFlow, sniffFlowText } from '../flowFile'
import type { Recipe } from '../types'

function sampleRecipe(): Recipe {
  return {
    version: 1,
    name: '舊名',
    nodes: [
      { id: 'input-1', kind: 'input', params: {}, position: { x: 60, y: 200 } },
      { id: 'n2-123', kind: 'tool', toolKey: 'video.transcode', params: { output_format: 'mp4' }, position: { x: 300, y: 200 }, keepOutput: true },
    ],
    edges: [{ from: 'input-1', to: 'n2-123' }],
  }
}

describe('flowFile', () => {
  it('serialize→parse 往返結構等價，name 以參數為準（雙注入）', () => {
    const text = serializeFlow('新名', sampleRecipe())
    const env = JSON.parse(text)
    expect(env.format).toBe(FLOW_FORMAT)
    expect(env.version).toBe(1)
    expect(env.name).toBe('新名')
    const parsed = parseFlow(text)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    expect(parsed.name).toBe('新名')
    expect(parsed.recipe.name).toBe('新名')     // 重建 Recipe 注入 name
    expect(parsed.recipe.version).toBe(1)
    expect(parsed.recipe.nodes).toEqual(sampleRecipe().nodes)
    expect(parsed.recipe.edges).toEqual(sampleRecipe().edges)
  })

  it('serialize 不夾帶 run 狀態欄位（信封只有 format/version/name/recipe）', () => {
    const env = JSON.parse(serializeFlow('x', sampleRecipe()))
    expect(Object.keys(env).sort()).toEqual(['format', 'name', 'recipe', 'version'])
    expect(Object.keys(env.recipe).sort()).toEqual(['edges', 'nodes'])
  })

  it('壞 JSON → bad_json', () => {
    expect(parseFlow('{oops')).toEqual({ ok: false, error: 'bad_json' })
  })

  it('format 不符 → bad_format', () => {
    expect(parseFlow(JSON.stringify({ format: 'x', version: 1, name: '', recipe: { nodes: [], edges: [] } })))
      .toEqual({ ok: false, error: 'bad_format' })
  })

  it('version 缺/非整數/過新 → 對應錯誤', () => {
    const base = { format: FLOW_FORMAT, name: '', recipe: { nodes: [], edges: [] } }
    expect(parseFlow(JSON.stringify({ ...base }))).toEqual({ ok: false, error: 'bad_format' })          // 缺 version
    expect(parseFlow(JSON.stringify({ ...base, version: 1.5 }))).toEqual({ ok: false, error: 'bad_format' })
    expect(parseFlow(JSON.stringify({ ...base, version: 0 }))).toEqual({ ok: false, error: 'bad_format' })
    expect(parseFlow(JSON.stringify({ ...base, version: 2 }))).toEqual({ ok: false, error: 'version_too_new' })
  })

  it('recipe 缺 nodes/edges 陣列 → bad_format', () => {
    expect(parseFlow(JSON.stringify({ format: FLOW_FORMAT, version: 1, name: '', recipe: {} })))
      .toEqual({ ok: false, error: 'bad_format' })
  })

  it('nodes/edges 含非物件元素（null/number）→ bad_format（下游會 crash、邊界擋）', () => {
    const base = { format: FLOW_FORMAT, version: 1, name: '' }
    expect(parseFlow(JSON.stringify({ ...base, recipe: { nodes: [null], edges: [] } })))
      .toEqual({ ok: false, error: 'bad_format' })
    expect(parseFlow(JSON.stringify({ ...base, recipe: { nodes: [], edges: [123] } })))
      .toEqual({ ok: false, error: 'bad_format' })
    expect(parseFlow(JSON.stringify({ ...base, recipe: { nodes: [[]], edges: [] } })))
      .toEqual({ ok: false, error: 'bad_format' })
  })

  it('信封缺 name → recipe.name/name 回退為空字串', () => {
    const r = parseFlow(JSON.stringify({ format: FLOW_FORMAT, version: 1, recipe: { nodes: [], edges: [] } }))
    expect(r).toEqual({ ok: true, name: '', recipe: { version: 1, name: '', nodes: [], edges: [] } })
  })

  it('isFlowFileName / sniffFlowText', () => {
    expect(isFlowFileName('a.mtxflow')).toBe(true)
    expect(isFlowFileName('A.MTXFLOW')).toBe(true)
    expect(isFlowFileName('a.json')).toBe(false)
    expect(sniffFlowText(serializeFlow('x', sampleRecipe()))).toBe(true)
    expect(sniffFlowText('{"format":"other"}')).toBe(false)
    expect(sniffFlowText('not json')).toBe(false)
  })
})
