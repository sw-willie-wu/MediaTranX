/**
 * 模型需求 × 已安裝模型清單的比對純函式（統一參數元件 spec；批 1 Task 1.6 抽出）。
 * 原本 inline 在 ToolParamHost.preflight()——現與 pipeline store 的 startRun 前驗證共用
 * 同一份比對邏輯，避免兩處漂移。
 *
 * variant 格式 'size:quantization'（如 '4b:Q4_K_M'）；quantization 段可空。
 */

/** modelStore.models 元素的最小形狀（避免此檔直接依賴 stores/models 型別，維持純函式） */
export interface ModelGuardEntry {
  family: string
  variant: string
  downloaded: boolean
}

export interface ModelGuardRequirement {
  slot: string
  family?: string
  size?: string
  quantization?: string
}

/** requirement 是否已有對應的已安裝模型（family + size 相符，quantization 若指定則需相符）。 */
export function isModelInstalled(
  models: ModelGuardEntry[],
  req: ModelGuardRequirement,
): boolean {
  return models.some((m) => {
    if (m.family !== req.family) return false
    const [size, quant] = m.variant.split(':')
    if (size !== req.size) return false
    if (req.quantization && quant !== req.quantization) return false
    return m.downloaded
  })
}
