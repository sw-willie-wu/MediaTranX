/**
 * 模型需求 × 已安裝模型清單的比對純函式（統一參數元件 spec；批 1 Task 1.6 抽出，
 * 批 2 Task 2.3 擴充 variant 型比對）。
 * 原本 inline 在 ToolParamHost.preflight()——現與 pipeline store 的 startRun 前驗證共用
 * 同一份比對邏輯，避免兩處漂移。
 *
 * 三種比對形狀：
 * - family/size/quantization：req.variant 未定義且 req.family/req.size 至少一個有值時走此
 *   分支；variant 格式 'size:quantization'（如 '4b:Q4_K_M'）；quantization 段可空（未指定＝
 *   萬用，任一量化命中即可——translate 等既有路徑，行為不變）。
 * - variant/categories：req.variant 有定義；variant 是純 token（如 RIFE 的 'v4.26'、
 *   Real-ESRGAN 的 'x4plus'），不做 size:quantization 拆解；categories 限定 modelStore
 *   category/subcategory 查找範圍（對照 modelStore.byCategory 的
 *   `category === c || subcategory === c` 語意），family 選配（僅在需要跨 category 收斂
 *   同家族時使用，如 enhance 的 realesrgan）。
 * - categories-only（批 2 Task 2.4 擴充）：req.variant 未定義且 req.family/req.size 皆未定義、
 *   只給 categories——categories 內任一 downloaded 模型即視為就緒（summary 的 wav2vec2
 *   forced-alignment 用：任一已裝的 alignment 模型即可，無特定 family/variant 要求）。
 */

/** modelStore.models 元素的最小形狀（避免此檔直接依賴 stores/models 型別，維持純函式） */
export interface ModelGuardEntry {
  family: string
  variant: string
  downloaded: boolean
  category?: string
  subcategory?: string
}

export interface ModelGuardRequirement {
  slot: string
  family?: string
  size?: string
  quantization?: string
  variant?: string
  categories?: string[]
}

/** requirement 是否已有對應的已安裝模型。 */
export function isModelInstalled(
  models: ModelGuardEntry[],
  req: ModelGuardRequirement,
): boolean {
  if (req.variant !== undefined) {
    return models.some((m) => {
      if (req.family !== undefined && m.family !== req.family) return false
      if (req.categories && req.categories.length > 0) {
        const inScope = req.categories.includes(m.category ?? '') || req.categories.includes(m.subcategory ?? '')
        if (!inScope) return false
      }
      return m.variant === req.variant && m.downloaded
    })
  }
  // categories-only：無 variant 也無 family/size，僅靠 categories 收斂——任一 downloaded 即就緒
  if (req.family === undefined && req.size === undefined && req.categories && req.categories.length > 0) {
    return models.some((m) => {
      const inScope = req.categories!.includes(m.category ?? '') || req.categories!.includes(m.subcategory ?? '')
      return inScope && m.downloaded
    })
  }
  // family + size 相符，quantization 若指定則需相符（既有路徑，未動）
  return models.some((m) => {
    if (m.family !== req.family) return false
    const [size, quant] = m.variant.split(':')
    if (size !== req.size) return false
    if (req.quantization && quant !== req.quantization) return false
    return m.downloaded
  })
}
