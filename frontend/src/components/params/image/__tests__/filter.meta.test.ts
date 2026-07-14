/**
 * image.filter META 單測（統一參數元件 spec §4；批 4 Task 4.2）。
 * 11 欄全集（adjust 6 + filter 5）defaults／中性值；agentRequiresConfirm 選配欄位。
 */
import { describe, it, expect } from 'vitest'
import { META } from '../filter.meta'

describe('image.filter META', () => {
  it('schema 有 11 欄，順序＝adjust 6 欄接 filter 5 欄', () => {
    expect(META.schema.map((f) => f.name)).toEqual([
      'brightness', 'contrast', 'saturation', 'hue', 'sharpness', 'warmth',
      'grayscale', 'sepia', 'invert', 'blur', 'vignette',
    ])
  })

  it('defaults()＝11 欄中性值（brightness/contrast/saturation/sharpness=1.0，其餘=0）', () => {
    expect(META.defaults()).toEqual({
      brightness: 1.0,
      contrast: 1.0,
      saturation: 1.0,
      hue: 0,
      sharpness: 1.0,
      warmth: 0,
      grayscale: 0,
      sepia: 0,
      invert: 0,
      blur: 0,
      vignette: 0,
    })
  })

  it('每個欄位皆 type=number，min/max/step 沿 registry 現值（後端尺度）', () => {
    const byName = Object.fromEntries(META.schema.map((f) => [f.name, f]))
    expect(byName.brightness).toMatchObject({ type: 'number', min: 0, max: 3, step: 0.05 })
    expect(byName.contrast).toMatchObject({ type: 'number', min: 0, max: 3, step: 0.05 })
    expect(byName.saturation).toMatchObject({ type: 'number', min: 0, max: 3, step: 0.05 })
    expect(byName.sharpness).toMatchObject({ type: 'number', min: 0, max: 3, step: 0.05 })
    expect(byName.hue).toMatchObject({ type: 'number', min: -180, max: 180, step: 1 })
    expect(byName.warmth).toMatchObject({ type: 'number', min: -1, max: 1, step: 0.05 })
    expect(byName.grayscale).toMatchObject({ type: 'number', min: 0, max: 1, step: 0.05 })
    expect(byName.sepia).toMatchObject({ type: 'number', min: 0, max: 1, step: 0.05 })
    expect(byName.invert).toMatchObject({ type: 'number', min: 0, max: 1, step: 0.05 })
    expect(byName.blur).toMatchObject({ type: 'number', min: 0, max: 100, step: 0.5 })
    expect(byName.vignette).toMatchObject({ type: 'number', min: 0, max: 1, step: 0.05 })
  })

  it('agentRequiresConfirm=false（沿舊 ImageAdjustPanel／ImageFilterPanel 兩者皆 false）', () => {
    expect(META.agentRequiresConfirm).toBe(false)
  })

  it('multiSelect=true（舊 ImageView.handleMultiExecute 已支援 adjust/filter 批次）', () => {
    expect(META.multiSelect).toBe(true)
  })

  it('labelKey/taskType/apiPath 沿 registry 現值', () => {
    expect(META.toolKey).toBe('image.filter')
    expect(META.apiPath).toBe('/image/filter')
    expect(META.labelKey).toBe('image.filter.task_label')
    expect(META.taskType).toBe('image.filter')
  })

  it('無 buildSubmit/modelRequirement/downloadFormatField/seedOnFileChange（純數值調整工具）', () => {
    expect(META.buildSubmit).toBeUndefined()
    expect(META.modelRequirement).toBeUndefined()
    expect(META.modelRequirements).toBeUndefined()
    expect(META.downloadFormatField).toBeUndefined()
    expect(META.seedOnFileChange).toBeUndefined()
  })
})
