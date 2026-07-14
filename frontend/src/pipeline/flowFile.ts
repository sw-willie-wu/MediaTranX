/**
 * .mtxflow 流程檔信封（spec §2）。純函式——store/view 皆經此進出。
 * 信封 name 是唯一權威名:serialize 雙注入（信封＋recipe 副本）、
 * parse 重建完整 Recipe（型別要求 version/name）。
 */
import type { Recipe, RecipeEdge, RecipeNode } from './types'

export const FLOW_FORMAT = 'mediatranx-pipeline'
export const FLOW_VERSION = 1

export type FlowParseError = 'bad_json' | 'bad_format' | 'version_too_new'

export function serializeFlow(name: string, recipe: Recipe): string {
  // 外層 stringify 即完整快照，nodes/edges 不需先 deep-clone
  return JSON.stringify({
    format: FLOW_FORMAT,
    version: FLOW_VERSION,
    name,
    recipe: { nodes: recipe.nodes, edges: recipe.edges },
  }, null, 2)
}

export function parseFlow(text: string):
  | { ok: true; name: string; recipe: Recipe }
  | { ok: false; error: FlowParseError } {
  let raw: unknown
  try { raw = JSON.parse(text) } catch { return { ok: false, error: 'bad_json' } }
  if (typeof raw !== 'object' || raw === null) return { ok: false, error: 'bad_format' }
  const env = raw as Record<string, unknown>
  if (env.format !== FLOW_FORMAT) return { ok: false, error: 'bad_format' }
  const v = env.version
  if (typeof v !== 'number' || !Number.isInteger(v) || v < 1) return { ok: false, error: 'bad_format' }
  if (v > FLOW_VERSION) return { ok: false, error: 'version_too_new' }
  const rec = env.recipe as Record<string, unknown> | undefined
  // 元素級「內容」驗證下放 normalizeParams/validateRecipe，但「非物件」元素
  // （null/number/string）下游會 crash 而非降級——結構性壞檔在 parse 邊界擋掉
  const allObjects = (a: unknown[]) => a.every(x => typeof x === 'object' && x !== null && !Array.isArray(x))
  if (!rec || !Array.isArray(rec.nodes) || !Array.isArray(rec.edges)
      || !allObjects(rec.nodes) || !allObjects(rec.edges)) {
    return { ok: false, error: 'bad_format' }
  }
  const name = typeof env.name === 'string' ? env.name : ''
  return {
    ok: true,
    name,
    recipe: {
      version: 1,
      name,
      nodes: rec.nodes as RecipeNode[],
      edges: rec.edges as RecipeEdge[],
    },
  }
}

export function isFlowFileName(filename: string): boolean {
  return filename.toLowerCase().endsWith('.mtxflow')
}

export function sniffFlowText(text: string): boolean {
  try {
    const raw = JSON.parse(text) as Record<string, unknown>
    return raw?.format === FLOW_FORMAT
  } catch { return false }
}
