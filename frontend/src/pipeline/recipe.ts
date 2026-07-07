/**
 * Recipe 驗證（spec B1）——畫布連線、revalidate-on-load、agent create_pipeline
 * 三方共用同一函式。規則:無環、tool 入度恰 1（禁匯流）、恰一根（input 或
 * source 擇一）、edge 端點存在、媒體類別相容、params 過 paramSchema。
 */
import type { ParamField, Recipe, RecipeNode, ToolSpec, ValidationIssue } from './types'

export function validateRecipe(
  recipe: Recipe,
  registry: Record<string, ToolSpec>,
): ValidationIssue[] {
  const issues: ValidationIssue[] = []
  const nodeById = new Map<string, RecipeNode>()
  for (const n of recipe.nodes) nodeById.set(n.id, n)

  // ── 節點層 ──────────────────────────────────────────────────────
  for (const n of recipe.nodes) {
    if (n.kind === 'input') continue
    const spec = n.toolKey ? registry[n.toolKey] : undefined
    if (!spec) {
      issues.push({ severity: 'error', nodeId: n.id, code: 'unknown_tool', message: `unknown tool: ${n.toolKey}` })
      continue
    }
    if (n.kind === 'source' && spec.kind !== 'source') {
      issues.push({ severity: 'error', nodeId: n.id, code: 'unknown_tool', message: `${n.toolKey} is not a source tool` })
    }
    const { issues: paramIssues } = normalizeParams(n.params, spec, n.id)
    issues.push(...paramIssues)
  }

  // ── edge 端點 ───────────────────────────────────────────────────
  const validEdges = []
  for (const e of recipe.edges) {
    if (!nodeById.has(e.from) || !nodeById.has(e.to)) {
      issues.push({ severity: 'error', edge: e, code: 'edge_endpoint', message: `edge ${e.from}→${e.to} has missing endpoint` })
      continue
    }
    validEdges.push(e)
  }

  // ── 度數 ────────────────────────────────────────────────────────
  const indeg = new Map<string, number>()
  for (const n of recipe.nodes) indeg.set(n.id, 0)
  for (const e of validEdges) indeg.set(e.to, (indeg.get(e.to) ?? 0) + 1)

  // 有出邊/入邊的節點集合（孤立節點另行 warning,不重複報 in-degree 錯）
  const connected = new Set<string>()
  for (const e of validEdges) { connected.add(e.from); connected.add(e.to) }

  for (const n of recipe.nodes) {
    const d = indeg.get(n.id) ?? 0
    if (n.kind === 'tool' && d > 1) {
      issues.push({ severity: 'error', nodeId: n.id, code: 'tool_indegree', message: `tool node ${n.id} has in-degree ${d} (merge not supported)` })
    }
    // 入度 0 但有出邊的 tool 節點:不是孤立、也不是根——引擎永遠不會執行它,
    // 必須擋下（否則 run 靜默略過整條分支還回報成功）。
    if (n.kind === 'tool' && d === 0 && connected.has(n.id)) {
      issues.push({ severity: 'error', nodeId: n.id, code: 'tool_indegree', message: `tool node ${n.id} has no incoming edge (branch would never run)` })
    }
    if ((n.kind === 'input' || n.kind === 'source') && d > 0) {
      issues.push({ severity: 'error', nodeId: n.id, code: 'source_has_input', message: `${n.kind} node ${n.id} must not have incoming edges` })
    }
  }

  // ── 恰一根 ──────────────────────────────────────────────────────
  const roots = recipe.nodes.filter(n => n.kind === 'input' || n.kind === 'source')
  if (roots.length === 0) {
    issues.push({ severity: 'error', code: 'no_root', message: 'recipe needs exactly one input or source root' })
  } else if (roots.length > 1) {
    issues.push({ severity: 'error', code: 'multi_root', message: 'only one root (input or source) is supported in v1' })
  }

  // ── 無環（DFS 三色）─────────────────────────────────────────────
  const adj = new Map<string, string[]>()
  for (const e of validEdges) {
    const arr = adj.get(e.from) ?? []
    arr.push(e.to)
    adj.set(e.from, arr)
  }
  const color = new Map<string, 0 | 1 | 2>()
  let cycle = false
  const dfs = (id: string) => {
    if (cycle) return
    color.set(id, 1)
    for (const next of adj.get(id) ?? []) {
      const c = color.get(next) ?? 0
      if (c === 1) { cycle = true; return }
      if (c === 0) dfs(next)
    }
    color.set(id, 2)
  }
  for (const n of recipe.nodes) {
    if ((color.get(n.id) ?? 0) === 0) dfs(n.id)
  }
  if (cycle) {
    issues.push({ severity: 'error', code: 'cycle', message: 'recipe graph contains a cycle' })
  }

  // ── 媒體類別相容（僅 tool→tool / root→tool；上游 outputKind ∈ 下游 inputKinds）──
  if (!cycle) {
    for (const e of validEdges) {
      const from = nodeById.get(e.from)!
      const to = nodeById.get(e.to)!
      if (to.kind !== 'tool') continue
      const toSpec = to.toolKey ? registry[to.toolKey] : undefined
      if (!toSpec) continue
      let upKind: string | null = null
      if (from.kind === 'input') {
        upKind = null   // 使用者檔案類別 run 時才知道——連線時不擋，執行時由引擎過濾
      } else {
        const fromSpec = from.toolKey ? registry[from.toolKey] : undefined
        if (!fromSpec) continue
        upKind = fromSpec.outputKind(from.params)
      }
      if (upKind !== null && !toSpec.inputKinds.includes(upKind as never)) {
        issues.push({
          severity: 'error', edge: e, code: 'kind_mismatch',
          message: `${e.from}(${upKind}) → ${e.to} expects ${toSpec.inputKinds.join('/')}`,
        })
        continue
      }
      // inputExts refinement:宣告了就以它為準。v1 白名單沒有任何工具產出
      // .pdf 等 refinement 副檔名 → tool/source 上游接 inputExts 節點必為
      // 不相容（input 根的檔案副檔名由引擎在 run 時過濾）。若未來有工具
      // 產出符合的副檔名,在 ToolSpec 增 outputExts 再放寬此規則。
      if (upKind !== null && toSpec.inputExts && toSpec.inputExts.length > 0) {
        issues.push({
          severity: 'error', edge: e, code: 'kind_mismatch',
          message: `${e.to} only accepts ${toSpec.inputExts.map(x => '.' + x).join('/')} — no pipeline tool produces these; connect it directly to an input root`,
        })
      }
    }
  }

  // ── 孤立節點（可存不可跑）──────────────────────────────────────
  if (recipe.nodes.length > 1) {
    for (const n of recipe.nodes) {
      if (!connected.has(n.id)) {
        issues.push({ severity: 'warning', nodeId: n.id, code: 'orphan_node', message: `node ${n.id} is not connected` })
      }
    }
  }

  return issues
}

/**
 * 參數正規化（revalidate-on-load 容錯）:未知參數剝除＋warning、缺項補
 * default、驗證不過回 param_invalid（error）。回傳的 params 是乾淨副本。
 */
export function normalizeParams(
  raw: Record<string, unknown>,
  spec: ToolSpec,
  nodeId?: string,
): { params: Record<string, unknown>; issues: ValidationIssue[] } {
  const issues: ValidationIssue[] = []
  const byName = new Map(spec.paramSchema.map(f => [f.name, f]))
  const params: Record<string, unknown> = {}

  for (const key of Object.keys(raw)) {
    if (!byName.has(key)) {
      issues.push({ severity: 'warning', nodeId, code: 'param_unknown', message: `unknown param '${key}' on ${spec.toolKey} (stripped)` })
    }
  }

  for (const field of spec.paramSchema) {
    const has = Object.prototype.hasOwnProperty.call(raw, field.name)
    const value = has ? raw[field.name] : field.default
    if (value === undefined) continue
    const err = _checkField(field, value)
    if (err) {
      issues.push({ severity: 'error', nodeId, code: 'param_invalid', message: `${spec.toolKey}.${field.name}: ${err}` })
      continue
    }
    // number 欄位存 coerce 後的值（agent 給 "24" 字串時後送乾淨數字）
    params[field.name] = field.type === 'number' ? Number(value) : value
  }
  return { params, issues }
}

function _checkField(field: ParamField, value: unknown): string | null {
  switch (field.type) {
    case 'enum':
      if (field.options && !field.options.includes(String(value))) {
        return `'${value}' not in [${field.options.join(', ')}]`
      }
      return null
    case 'number': {
      const n = Number(value)
      if (!Number.isFinite(n)) return `'${value}' is not a number`
      if (field.min !== undefined && n < field.min) return `${n} < min ${field.min}`
      if (field.max !== undefined && n > field.max) return `${n} > max ${field.max}`
      return null
    }
    case 'boolean':
      return typeof value === 'boolean' ? null : `'${value}' is not a boolean`
    case 'string':
      return typeof value === 'string' ? null : `'${value}' is not a string`
  }
}
