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
