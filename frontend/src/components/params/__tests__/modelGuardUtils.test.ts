/**
 * isModelInstalled 純函式單測（批 1 Task 1.6 抽出——原 inline 在 ToolParamHost.preflight，
 * 現與 pipeline store startRun 前驗證共用）。variant 格式 'size:quantization'。
 */
import { describe, it, expect } from 'vitest'
import { isModelInstalled, type ModelGuardEntry } from '../modelGuardUtils'

describe('isModelInstalled', () => {
  const models: ModelGuardEntry[] = [
    { family: 'gemma4', variant: '4b:Q4_K_M', downloaded: true },
    { family: 'gemma4', variant: '9b:Q4_K_M', downloaded: false },
    { family: 'llama3', variant: '8b:Q8_0', downloaded: true },
  ]

  it('family + size 相符且 quantization 相符、downloaded=true → true', () => {
    expect(isModelInstalled(models, { slot: 'translate', family: 'gemma4', size: '4b', quantization: 'Q4_K_M' })).toBe(true)
  })

  it('family 相符但 size 不同 → false', () => {
    expect(isModelInstalled(models, { slot: 'translate', family: 'gemma4', size: '9b', quantization: 'Q4_K_M' })).toBe(false)
    // size 9b 確實存在於清單但 downloaded=false —— 順便驗證這條也回 false
  })

  it('family 不存在 → false', () => {
    expect(isModelInstalled(models, { slot: 'translate', family: 'qwen', size: '4b' })).toBe(false)
  })

  it('size 相符但未下載 → false', () => {
    expect(isModelInstalled(models, { slot: 'translate', family: 'gemma4', size: '9b' })).toBe(false)
  })

  it('quantization 未指定 → 只比對 family/size，忽略 variant 的量化段', () => {
    expect(isModelInstalled(models, { slot: 'translate', family: 'llama3', size: '8b' })).toBe(true)
  })

  it('quantization 指定但與已安裝的不同 → false', () => {
    expect(isModelInstalled(models, { slot: 'translate', family: 'llama3', size: '8b', quantization: 'Q4_K_M' })).toBe(false)
  })

  it('空清單 → 恆 false', () => {
    expect(isModelInstalled([], { slot: 'translate', family: 'gemma4', size: '4b' })).toBe(false)
  })
})

describe('isModelInstalled — variant 型比對（批 2 Task 2.3 擴充）', () => {
  const models: ModelGuardEntry[] = [
    { family: 'rife', variant: 'v4.26', downloaded: true, category: 'interpolate' },
    { family: 'rife', variant: 'v4.22', downloaded: false, category: 'interpolate' },
    { family: 'realesrgan', variant: 'x4plus', downloaded: true, category: 'upscale' },
    { family: 'realesrgan', variant: 'x2plus', downloaded: false, category: 'upscale' },
    { family: 'realesrgan', variant: 'animevideov3', downloaded: true, subcategory: 'video_enhance' },
    { family: 'swinir', variant: 'lightweight-x4', downloaded: true, category: 'upscale' },
  ]

  it('variant 相符、categories 命中、downloaded=true → true（interpolate 案例）', () => {
    expect(isModelInstalled(models, { slot: 'interpolate', variant: 'v4.26', categories: ['interpolate'] })).toBe(true)
  })

  it('variant 相符但 downloaded=false → false', () => {
    expect(isModelInstalled(models, { slot: 'interpolate', variant: 'v4.22', categories: ['interpolate'] })).toBe(false)
  })

  it('variant 不存在於清單 → false', () => {
    expect(isModelInstalled(models, { slot: 'interpolate', variant: 'v5.0', categories: ['interpolate'] })).toBe(false)
  })

  it('categories 命中 category 或 subcategory 任一 → true（enhance 案例，animevideov3 掛 subcategory）', () => {
    expect(isModelInstalled(models, { slot: 'enhance', variant: 'animevideov3', family: 'realesrgan', categories: ['upscale', 'video_enhance'] })).toBe(true)
    expect(isModelInstalled(models, { slot: 'enhance', variant: 'x4plus', family: 'realesrgan', categories: ['upscale', 'video_enhance'] })).toBe(true)
  })

  it('family 指定但不符 → false（即使 variant/category 都命中，swinir 非 realesrgan）', () => {
    expect(isModelInstalled(models, { slot: 'enhance', variant: 'lightweight-x4', family: 'realesrgan', categories: ['upscale', 'video_enhance'] })).toBe(false)
  })

  it('categories 未提供時忽略 category 過濾，僅靠 family+variant 比對', () => {
    expect(isModelInstalled(models, { slot: 'enhance', variant: 'x4plus', family: 'realesrgan' })).toBe(true)
  })

  it('既有 family/size/quantization 路徑不回歸（req.variant 未定義時走舊分支）', () => {
    const legacyModels: ModelGuardEntry[] = [{ family: 'gemma4', variant: '4b:Q4_K_M', downloaded: true }]
    expect(isModelInstalled(legacyModels, { slot: 'translate', family: 'gemma4', size: '4b', quantization: 'Q4_K_M' })).toBe(true)
    expect(isModelInstalled(legacyModels, { slot: 'translate', family: 'gemma4', size: '9b' })).toBe(false)
  })
})

describe('isModelInstalled — categories-only 比對（批 2 Task 2.4 擴充，align 用）', () => {
  const models: ModelGuardEntry[] = [
    { family: 'wav2vec2', variant: 'base', downloaded: true, category: 'alignment' },
    { family: 'wav2vec2', variant: 'large', downloaded: false, category: 'alignment' },
    { family: 'demucs', variant: 'htdemucs_6s', downloaded: true, category: 'separate' },
  ]

  it('無 variant 無 family/size，categories 內任一 downloaded → true', () => {
    expect(isModelInstalled(models, { slot: 'align', categories: ['alignment'] })).toBe(true)
  })

  it('categories 內全數未下載 → false', () => {
    const noneDownloaded: ModelGuardEntry[] = [
      { family: 'wav2vec2', variant: 'base', downloaded: false, category: 'alignment' },
    ]
    expect(isModelInstalled(noneDownloaded, { slot: 'align', categories: ['alignment'] })).toBe(false)
  })

  it('categories 未命中任何模型 → false', () => {
    expect(isModelInstalled(models, { slot: 'align', categories: ['nonexistent'] })).toBe(false)
  })

  it('categories 命中 subcategory 亦可（沿既有 variant 分支的 category||subcategory 語意）', () => {
    const subcatModels: ModelGuardEntry[] = [
      { family: 'wav2vec2', variant: 'base', downloaded: true, subcategory: 'alignment' },
    ]
    expect(isModelInstalled(subcatModels, { slot: 'align', categories: ['alignment'] })).toBe(true)
  })

  it('空 categories 陣列時不誤入此分支（family/size 皆 undefined 但 categories 為空 → 落回 family/size 分支，回 false）', () => {
    expect(isModelInstalled(models, { slot: 'align', categories: [] })).toBe(false)
  })

  it('quantization 未指定為萬用（既有事實補測試）：family/size 相符、忽略 variant 量化段', () => {
    const withQuant: ModelGuardEntry[] = [{ family: 'gemma4', variant: '4b:Q4_K_M', downloaded: true }]
    expect(isModelInstalled(withQuant, { slot: 'llm', family: 'gemma4', size: '4b' })).toBe(true)
  })
})
