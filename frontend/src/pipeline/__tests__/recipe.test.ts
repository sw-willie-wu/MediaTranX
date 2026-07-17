import { describe, it, expect } from 'vitest'
import { canConnect, reachableFromRoot, validateRecipe, normalizeParams } from '../recipe'
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

  it('flags tool node with in-degree 0 that has outgoing edges as tool_unrooted warning (not error)', () => {
    // 拆碼（2026-07-16 spec §0）：未生根子鏈是「還沒接到根」的狀態、非不合理圖——
    // 可達子圖執行語意下不擋 run、不擋連線；error 版會封死「先組子鏈再接根」
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: {} },
        { id: 'x', kind: 'tool', toolKey: 'video.transcode', params: {} },   // 無入邊
        { id: 'y', kind: 'tool', toolKey: 'video.transcode', params: {} },
      ],
      [{ from: 'n1', to: 'a' }, { from: 'x', to: 'y' }],   // x→y 尚未接根
    )
    expect(warnsOf(r)).toContain('tool_unrooted')
    expect(errsOf(r)).not.toContain('tool_indegree')
    expect(errsOf(r)).not.toContain('tool_unrooted')
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

describe('reachableFromRoot', () => {
  it('walks a straight chain and includes the root itself', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: {} },
        { id: 'b', kind: 'tool', toolKey: 'image.compress', params: {} },
      ],
      [{ from: 'n1', to: 'a' }, { from: 'a', to: 'b' }],
    )
    expect(reachableFromRoot(r)).toEqual(new Set(['n1', 'a', 'b']))
  })

  it('covers branches (out-tree) from a source root', () => {
    const r = recipe(
      [
        { id: 's', kind: 'source', toolKey: 'video.download', params: { url: 'x' } },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: {} },
        { id: 'b', kind: 'tool', toolKey: 'video.transcode', params: {} },
      ],
      [{ from: 's', to: 'a' }, { from: 's', to: 'b' }],
    )
    expect(reachableFromRoot(r)).toEqual(new Set(['s', 'a', 'b']))
  })

  it('excludes orphans and unrooted chains', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: {} },
        { id: 'x', kind: 'tool', toolKey: 'video.transcode', params: {} },
        { id: 'y', kind: 'tool', toolKey: 'video.transcode', params: {} },
        { id: 'lone', kind: 'tool', toolKey: 'image.compress', params: {} },
      ],
      [{ from: 'n1', to: 'a' }, { from: 'x', to: 'y' }],
    )
    expect(reachableFromRoot(r)).toEqual(new Set(['n1', 'a']))
  })

  it('returns empty set with no root, and walks only the first root with two roots', () => {
    const none = recipe(
      [{ id: 'a', kind: 'tool', toolKey: 'video.transcode', params: {} }],
      [],
    )
    expect(reachableFromRoot(none)).toEqual(new Set())
    // 雙根：與 runner.start() 同規則——nodes 序上第一個根
    const two = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 's', kind: 'source', toolKey: 'video.download', params: { url: 'x' } },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: {} },
        { id: 'b', kind: 'tool', toolKey: 'video.transcode', params: {} },
      ],
      [{ from: 'n1', to: 'a' }, { from: 's', to: 'b' }],
    )
    expect(reachableFromRoot(two)).toEqual(new Set(['n1', 'a']))
  })
})

describe('canConnect', () => {
  const chain = () => recipe(
    [
      { id: 'n1', kind: 'input', params: {} },
      { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: { output_format: 'gif' } },
      { id: 'b', kind: 'tool', toolKey: 'image.compress', params: {} },
    ],
    [{ from: 'n1', to: 'a' }],
  )

  it('allows a legal tool→tool connection and does not mutate the recipe', () => {
    const r = chain()
    const edgesBefore = r.edges.length
    expect(canConnect(r, 'a', 'b', REG)).toBeNull()
    expect(r.edges.length).toBe(edgesBefore)
  })

  it('allows root→tool', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: {} },
      ],
      [],
    )
    expect(canConnect(r, 'n1', 'a', REG)).toBeNull()
  })

  it('rejects tool→root (source_has_input)', () => {
    // 注意用 b→n1（無環路徑）:a→n1 會先被成環檢查攔下（n1→a 既存）
    const r = chain()
    expect(canConnect(r, 'b', 'n1', REG)).toMatch(/must not have incoming/)
  })

  it('rejects tool→root that would also close a cycle with the cycle message', () => {
    const r = chain()
    expect(canConnect(r, 'a', 'n1', REG)).toMatch(/cycle/)
  })

  it('rejects kind mismatch (image output → video-only input)', () => {
    // a 產出 gif（image）、video.transcode 只吃 video
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'video.transcode', params: { output_format: 'gif' } },
        { id: 'v', kind: 'tool', toolKey: 'video.transcode', params: {} },
      ],
      [{ from: 'n1', to: 'a' }],
    )
    expect(canConnect(r, 'a', 'v', REG)).toMatch(/expects/)
  })

  it('rejects duplicate edges', () => {
    const r = chain()
    expect(canConnect(r, 'n1', 'a', REG)).toMatch(/already exists/)
  })

  it('rejects self-loop and back-edge cycles', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'image.compress', params: {} },
        { id: 'b', kind: 'tool', toolKey: 'image.compress', params: {} },
      ],
      [{ from: 'n1', to: 'a' }, { from: 'a', to: 'b' }],
    )
    expect(canConnect(r, 'a', 'a', REG)).toMatch(/cycle/)
    expect(canConnect(r, 'b', 'a', REG)).toMatch(/cycle/)
  })

  it('rejects a second cycle-closing edge even when the graph already contains a cycle', () => {
    // 差集法對 cycle 只 push 一次會漏判（spec §F4-③）——成環走專用檢查
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'image.compress', params: {} },
        { id: 'b', kind: 'tool', toolKey: 'image.compress', params: {} },
        { id: 'c', kind: 'tool', toolKey: 'image.compress', params: {} },
        { id: 'd', kind: 'tool', toolKey: 'image.compress', params: {} },
      ],
      [
        { from: 'n1', to: 'a' },
        { from: 'a', to: 'b' }, { from: 'b', to: 'a' },      // 既有環（如匯入檔）
        { from: 'c', to: 'd' },
      ],
    )
    expect(canConnect(r, 'd', 'c', REG)).toMatch(/cycle/)
  })

  it('rejects merge (in-degree > 1) via node-scoped diff', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'image.compress', params: {} },
        { id: 'b', kind: 'tool', toolKey: 'image.compress', params: {} },
      ],
      [{ from: 'n1', to: 'a' }, { from: 'n1', to: 'b' }],
    )
    expect(canConnect(r, 'a', 'b', REG)).toMatch(/in-degree/)
  })

  it('allows connecting two isolated tools (unrooted subchain is legal)', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'x', kind: 'tool', toolKey: 'image.compress', params: {} },
        { id: 'y', kind: 'tool', toolKey: 'image.compress', params: {} },
      ],
      [],
    )
    expect(canConnect(r, 'x', 'y', REG)).toBeNull()
  })

  it('is not confused by pre-existing dangling-endpoint edges elsewhere', () => {
    const r = recipe(
      [
        { id: 'n1', kind: 'input', params: {} },
        { id: 'a', kind: 'tool', toolKey: 'image.compress', params: {} },
        { id: 'b', kind: 'tool', toolKey: 'image.compress', params: {} },
      ],
      [{ from: 'n1', to: 'a' }, { from: 'ghost', to: 'b' }],   // 懸空 id（壞檔匯入）
    )
    expect(canConnect(r, 'a', 'b', REG)).toBeNull()
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
