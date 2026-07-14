/**
 * CompressParams.vue 單測（統一參數元件 spec §5；批 4 Task 4.1）。
 * 覆蓋：palette 動態上限、換圖重置（fileInfo 形狀 key）、userTouched 值不被同圖 patch 清掉、
 * png_lossy↔png_mode UI 衍生、resultMeta fallthrough 顯示、格式條件顯示區塊。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string, params?: Record<string, unknown>) => (params ? `${k}:${JSON.stringify(params)}` : k) }),
}))

import CompressParams from '../CompressParams.vue'
import AppRange from '@/components/common/AppRange.vue'
import AppSelect from '@/components/common/AppSelect.vue'

function mockT(k: string, params?: Record<string, unknown>): string {
  return params ? `${k}:${JSON.stringify(params)}` : k
}

function mountParams(
  params: Record<string, unknown>,
  extra: Record<string, unknown> = {},
  context: 'tool' | 'pipeline' = 'tool',
) {
  return mount(CompressParams, {
    props: { params, context, fileInfo: null, ...extra },
    global: { mocks: { $t: mockT } },
  })
}

const gifInfoA = { width: 200, height: 100, format: 'GIF', mode: 'P', file_size: 5000, palette_size: 100 }
const gifInfoB = { width: 150, height: 80, format: 'GIF', mode: 'P', file_size: 3000, palette_size: 40 }
const pngInfo = { width: 100, height: 100, format: 'PNG', mode: 'RGBA', file_size: 1000 }
const jpegInfo = { width: 100, height: 100, format: 'JPEG', mode: 'RGB', file_size: 1000 }
const webpInfo = { width: 100, height: 100, format: 'WEBP', mode: 'RGB', file_size: 1000 }

describe('CompressParams — 頂層 strength', () => {
  it('顯示 params.strength', () => {
    const w = mountParams({ strength: 75 })
    expect(w.text()).toContain('75')
  })

  it('AppRange 拖動 → emit update:params 帶新 strength', async () => {
    const w = mountParams({ strength: 75 })
    const range = w.findComponent(AppRange)
    range.vm.$emit('update:modelValue', 40)
    await w.vm.$nextTick()
    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toMatchObject({ strength: 40 })
  })
})

describe('CompressParams — 格式條件顯示（依 fileInfo.format）', () => {
  it('GIF → 顯示 GIF 進階區，不顯示 PNG/JPEG/WEBP 區', () => {
    const w = mountParams({}, { fileInfo: gifInfoA })
    expect(w.text()).toContain('image.compress.gif_colors')
    expect(w.text()).not.toContain('image.compress.png_mode')
    expect(w.text()).not.toContain('image.compress.jpeg_progressive')
    expect(w.text()).not.toContain('image.compress.webp_lossless')
  })

  it('PNG → 顯示 png_mode 區', () => {
    const w = mountParams({}, { fileInfo: pngInfo })
    expect(w.text()).toContain('image.compress.png_mode')
  })

  it('JPEG → 顯示 jpeg_progressive/jpeg_keep_metadata 區', () => {
    const w = mountParams({}, { fileInfo: jpegInfo })
    expect(w.text()).toContain('image.compress.jpeg_progressive')
    expect(w.text()).toContain('image.compress.jpeg_keep_metadata')
  })

  it('WEBP → 顯示 webp_lossless 區', () => {
    const w = mountParams({}, { fileInfo: webpInfo })
    expect(w.text()).toContain('image.compress.webp_lossless')
  })

  it('fileInfo=null → 不顯示任何格式專屬進階區', () => {
    const w = mountParams({})
    expect(w.text()).not.toContain('image.compress.png_mode')
    expect(w.text()).not.toContain('image.compress.gif_colors')
  })
})

describe('CompressParams — png_lossy ↔ png_mode UI 衍生', () => {
  it('params.png_lossy=true → AppSelect 顯示 lossy', () => {
    const w = mountParams({ png_lossy: true }, { fileInfo: pngInfo })
    const select = w.findAllComponents(AppSelect).find((s) => ['lossy', 'lossless'].includes(s.props('modelValue')))!
    expect(select.props('modelValue')).toBe('lossy')
  })

  it('params.png_lossy=false → AppSelect 顯示 lossless', () => {
    const w = mountParams({ png_lossy: false }, { fileInfo: pngInfo })
    const select = w.findAllComponents(AppSelect).find((s) => ['lossy', 'lossless'].includes(s.props('modelValue')))!
    expect(select.props('modelValue')).toBe('lossless')
  })

  it('選 lossless → emit update:params { png_lossy: false }', async () => {
    const w = mountParams({ png_lossy: true }, { fileInfo: pngInfo })
    const select = w.findAllComponents(AppSelect).find((s) => ['lossy', 'lossless'].includes(s.props('modelValue')))!
    select.vm.$emit('update:modelValue', 'lossless')
    await w.vm.$nextTick()
    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toMatchObject({ png_lossy: false })
  })
})

describe('CompressParams — resultMeta fallthrough（沿 CropParams canvasCropRect 先例）', () => {
  it('resultMeta.saved_ratio=0.42 → 顯示 42% 節省摘要', () => {
    const w = mountParams({}, { resultMeta: { saved_ratio: 0.42, output_size: 5800, original_size: 10000 } })
    expect(w.find('.compress-result-summary').exists()).toBe(true)
    expect(w.find('.compress-result-summary').classes()).toContain('compress-result-saved')
  })

  it('resultMeta.saved_ratio<0 → larger 摘要，非 saved class', () => {
    const w = mountParams({}, { resultMeta: { saved_ratio: -0.3, output_size: 13000, original_size: 10000 } })
    expect(w.find('.compress-result-summary').classes()).not.toContain('compress-result-saved')
  })

  it('resultMeta=null → 不顯示摘要區', () => {
    const w = mountParams({}, { resultMeta: null })
    expect(w.find('.compress-result-summary').exists()).toBe(false)
  })

  it('resultMeta 無 saved_ratio → 不顯示摘要區', () => {
    const w = mountParams({}, { resultMeta: { some_other_field: 'x' } })
    expect(w.find('.compress-result-summary').exists()).toBe(false)
  })
})

describe('CompressParams — palette 動態上限 + 換圖重置 + userTouched（⭐核心）', () => {
  it('GIF 掛載時 palette_size=100 → gif_colors 自動 seed 為 100（emit）', () => {
    const w = mountParams({}, { fileInfo: gifInfoA })
    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toMatchObject({ gif_colors: 100 })
  })

  it('GIF 無 palette_size → gif_colors 預設 256', () => {
    const w = mountParams({}, { fileInfo: { width: 100, height: 100, format: 'GIF', mode: 'P', file_size: 1000 } })
    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toMatchObject({ gif_colors: 256 })
  })

  it('gif_colors slider max = palette_size（100）', () => {
    const w = mountParams({ gif_colors: 100 }, { fileInfo: gifInfoA })
    // gif_colors AppRange 的 max prop 應等於 palette_size（[0]=strength, [1]=gif_colors）
    const gifRange = w.findAllComponents(AppRange)[1]
    expect(gifRange.props('max')).toBe(100)
  })

  it('使用者調整 gif_colors 至 30 後，同一張圖（fileInfo 重建物件、形狀不變）重新整理不清掉 30', async () => {
    const w = mountParams({ gif_colors: 100 }, { fileInfo: gifInfoA })
    const gifRange = w.findAllComponents(AppRange)[1]
    gifRange.vm.$emit('update:modelValue', 30)
    await w.vm.$nextTick()
    let emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toMatchObject({ gif_colors: 30 })

    // 模擬 host 把 emit 的新 params 回寫、同時 fileInfo 因 post-task reload 換了新物件參照
    // 但形狀（width/height/format/mode）不變
    await w.setProps({
      params: { ...emitted[emitted.length - 1][0] as Record<string, unknown> },
      fileInfo: { ...gifInfoA },
    })
    emitted = w.emitted('update:params')!
    // 不應再多 emit 一次把 gif_colors 改回 100（沒有新的 commit，或即使有也維持 30）
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.gif_colors).toBe(30)
  })

  it('切換到不同尺寸/palette 的新圖（gifInfoB）→ gif_colors 重置為新 palette_size（40）', async () => {
    const w = mountParams({ gif_colors: 30 }, { fileInfo: gifInfoA })
    await w.setProps({ params: { gif_colors: 30 }, fileInfo: gifInfoB })
    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toMatchObject({ gif_colors: 40 })
  })

  it('palette_size 稍後才到（二階段）：初始 undefined→256 預設，patch 進 100 後夾限/更新 max', async () => {
    const basic = { width: 200, height: 100, format: 'GIF', mode: 'P', file_size: 5000 }
    const w = mountParams({}, { fileInfo: basic })
    let emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toMatchObject({ gif_colors: 256 })

    await w.setProps({
      params: { ...(emitted[emitted.length - 1][0] as Record<string, unknown>) },
      fileInfo: { ...basic, palette_size: 100 },
    })
    // gif_colors 256 > 新 max 100 → 夾回 100
    emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toMatchObject({ gif_colors: 100 })
  })

  it('非 GIF 圖片掛載 → 不 emit gif_colors seed', () => {
    const w = mountParams({}, { fileInfo: pngInfo })
    const emitted = w.emitted('update:params')
    if (emitted) {
      for (const call of emitted) {
        expect((call[0] as Record<string, unknown>).gif_colors).toBeUndefined()
      }
    }
  })
})
