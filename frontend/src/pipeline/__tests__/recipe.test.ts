import { describe, it, expect } from 'vitest'
import { validateRecipe, normalizeParams } from '../recipe'
import type { Recipe } from '../types'
import type { ToolSpec } from '../types'

// 測試用迷你 registry（不依賴真 registry，規則測試與抄寫進度解耦）
const REG: Record<string, ToolSpec> = {
  'video.transcode': {
    toolKey: 'video.transcode', apiPath: '/video/transcode', labelKey: 'x', kind: 'tool',
    inputKinds: ['video'],
    outputKind: (p) => (p.output_format === 'gif' ? 'image' : 'video'),
    paramSchema: [
      { name: 'output_format', type: 'enum', options: ['mp4', 'gif'], default: 'mp4' },
      { name: 'fps', type: 'number', min: 1, max: 60, default: 12 },
    ],
  },
  'image.compress': {
    toolKey: 'image.compress', apiPath: '/image/compress', labelKey: 'x', kind: 'tool',
    inputKinds: ['image'],
    outputKind: () => 'image',
    paramSchema: [{ name: 'strength', type: 'number', min: 0, max: 100, default: 60 }],
  },
  'document.split': {
    toolKey: 'document.split', apiPath: '/document/split', labelKey: 'x', kind: 'tool',
    inputKinds: ['document'], inputExts: ['pdf'],
    outputKind: () => 'document',
    paramSchema: [{ name: 'pages', type: 'string', default: '' }],
  },
  'video.download': {
    toolKey: 'video.download', apiPath: '/video/download', labelKey: 'x', kind: 'source',
    inputKinds: [], outputKind: () => 'video',
    paramSchema: [{ name: 'url', type: 'string' }],
  },
}

function recipe(nodes: Recipe['nodes'], edges: Recipe['edges']): Recipe {
  return { version: 1, name: 't', nodes, edges }
}

const errsOf = (r: Recipe) => validateRecipe(r, REG).filter(i => i.severity === 'error').map(i => i.code)
const warnsOf = (r: Recipe) => validateRecipe(r, REG).filter(i => i.severity === 'warning').map(i => i.code)

describe('validateRecipe', () => {
  it('accepts a valid straight chain (input → transcode gif → compress)', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'n2', kind: 'tool', toolKey: 'video.transcode', params: { output_format: 'gif' } },
        { id: 'n3', kind: 'tool', toolKey: 'image.compress', params: {} },
      ],
      [{ from: 'n1', to: 'n2' }, { from: 'n2', to: 'n3' }],
    )
    expect(errsOf(r)).toEqual([])
  })

  it('accepts a source-rooted chain and branching (out-tree)', () => {
    const r = recipe(
      [
        { id: 's', kind: 'source', toolKey: 'video.download', params: { url: 'https://x' } },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: { output_format: 'gif' } },
        { id: 'b', kind: 'tool', toolKey: 'video.transcode', params: { output_format: 'mp4' } },
      ],
      [{ from: 's', to: 'a' }, { from: 's', to: 'b' }],
    )
    expect(errsOf(r)).toEqual([])
  })

  it('rejects cycles', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: {} },
        { id: 'b', kind: 'tool', toolKey: 'video.transcode', params: {} },
      ],
      [{ from: 'n1', to: 'a' }, { from: 'a', to: 'b' }, { from: 'b', to: 'a' }],
    )
    expect(errsOf(r)).toContain('cycle')
  })

  it('rejects multiple roots / no root', () => {
    const two = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 's', kind: 'source', toolKey: 'video.download', params: { url: 'x' } },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: {} },
      ],
      [{ from: 'n1', to: 'a' }],
    )
    expect(errsOf(two)).toContain('multi_root')
    const none = recipe(
      [{ id: 'a', kind: 'tool', toolKey: 'video.transcode', params: {} }],
      [],
    )
    expect(errsOf(none)).toContain('no_root')
  })

  it('rejects tool node with in-degree != 1 (merge forbidden)', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: {} },
        { id: 'b', kind: 'tool', toolKey: 'video.transcode', params: {} },
        { id: 'c', kind: 'tool', toolKey: 'video.transcode', params: {} },
      ],
      [
        { from: 'n1', to: 'a' }, { from: 'n1', to: 'b' },
        { from: 'a', to: 'c' }, { from: 'b', to: 'c' },   // 匯流
      ],
    )
    expect(errsOf(r)).toContain('tool_indegree')
  })

  it('rejects dangling edge endpoints and unknown tools', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'nope.tool', params: {} },
      ],
      [{ from: 'n1', to: 'a' }, { from: 'a', to: 'ghost' }],
    )
    const codes = errsOf(r)
    expect(codes).toContain('unknown_tool')
    expect(codes).toContain('edge_endpoint')
  })

  it('rejects media-kind mismatch (transcode mp4 → image.compress)', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: { output_format: 'mp4' } },
        { id: 'b', kind: 'tool', toolKey: 'image.compress', params: {} },
      ],
      [{ from: 'n1', to: 'a' }, { from: 'a', to: 'b' }],
    )
    expect(errsOf(r)).toContain('kind_mismatch')
  })

  it('rejects params failing schema; strips unknown params with warning', () => {
    const bad = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: { output_format: 'exe', fps: 999 } },
      ],
      [{ from: 'n1', to: 'a' }],
    )
    expect(errsOf(bad)).toContain('param_invalid')

    const unknown = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: { bogus: 1 } },
      ],
      [{ from: 'n1', to: 'a' }],
    )
    expect(warnsOf(unknown)).toContain('param_unknown')
    expect(errsOf(unknown)).toEqual([])
  })

  it('warns on orphan nodes (saveable, not runnable)', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: {} },
        { id: 'lone', kind: 'tool', toolKey: 'image.compress', params: {} },
      ],
      [{ from: 'n1', to: 'a' }],
    )
    expect(warnsOf(r)).toContain('orphan_node')
    expect(errsOf(r)).toEqual([])
  })

  it('rejects tool node with in-degree 0 that has outgoing edges (dead branch)', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: {} },
        { id: 'x', kind: 'tool', toolKey: 'video.transcode', params: {} },   // 無入邊
        { id: 'y', kind: 'tool', toolKey: 'video.transcode', params: {} },
      ],
      [{ from: 'n1', to: 'a' }, { from: 'x', to: 'y' }],   // x→y 分支永遠不會跑
    )
    expect(errsOf(r)).toContain('tool_indegree')
  })

  it('rejects tool/source upstream into an inputExts-refined node', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'document.split', params: {} },   // 產出非 pdf
        { id: 'b', kind: 'tool', toolKey: 'document.split', params: {} },   // 只吃 pdf
      ],
      [{ from: 'n1', to: 'a' }, { from: 'a', to: 'b' }],
    )
    expect(errsOf(r)).toContain('kind_mismatch')
  })

  it('allows input root directly into an inputExts-refined node', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'document.split', params: {} },
      ],
      [{ from: 'n1', to: 'a' }],
    )
    expect(errsOf(r)).toEqual([])   // 副檔名由引擎 run 時過濾
  })

  it('rejects source node with incoming edge', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: {} },
        { id: 's', kind: 'source', toolKey: 'video.download', params: { url: 'x' } },
      ],
      [{ from: 'n1', to: 'a' }, { from: 'a', to: 's' }],
    )
    expect(errsOf(r)).toContain('source_has_input')
  })
})

describe('normalizeParams (revalidate-on-load)', () => {
  it('fills defaults and strips unknowns', () => {
    const spec = REG['video.transcode']
    const { params, issues } = normalizeParams({ bogus: 1, fps: 24 }, spec)
    expect(params).toEqual({ output_format: 'mp4', fps: 24 })
    expect(issues.map(i => i.code)).toContain('param_unknown')
  })
})
