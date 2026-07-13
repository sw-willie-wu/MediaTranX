/**
 * EnhanceParams.vue 單測（統一參數元件案批 2 Task 2.3）。
 * 覆蓋：掛載載入模型清單、variant picker 過濾（family=realesrgan）、composite set 寫回
 * model+variant 兩欄、解析度預覽、tool/pipeline context 的 persisted seed 分流。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import type { AgentCompositeField } from '../../types'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

const modelsState = vi.hoisted(() => ({
  models: [] as Array<{ family: string; variant: string; label: string; downloaded: boolean; category?: string; subcategory?: string }>,
}))
const ensureLoadedMock = vi.hoisted(() => vi.fn())
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    byCategory: (cat: string) => modelsState.models.filter((m) => m.category === cat || m.subcategory === cat),
    forPanel: (items: unknown[]) => items,
    ensureLoaded: ensureLoadedMock,
  }),
}))

import EnhanceParams from '../EnhanceParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'

function mountParams(
  params: Record<string, unknown>,
  context: 'tool' | 'pipeline' = 'tool',
  fileInfo: Record<string, unknown> | null = null,
  onRegister?: (c: AgentCompositeField) => void,
) {
  return mount(EnhanceParams, {
    props: { params, context, fileInfo },
    global: {
      mocks: { $t: (k: string) => k },
      provide: {
        registerComposite: (c: AgentCompositeField) => {
          onRegister?.(c)
          return () => {}
        },
      },
    },
  })
}

beforeEach(() => {
  modelsState.models = []
  localStorage.clear()
  ensureLoadedMock.mockClear()
})

describe('EnhanceParams — 掛載時載入模型清單', () => {
  it('mount 後 modelStore.ensureLoaded 被呼叫', () => {
    mountParams({ model: 'realesrgan', variant: 'x4plus', output_format: 'mp4', video_codec: 'h264' })
    expect(ensureLoadedMock).toHaveBeenCalledTimes(1)
  })
})

describe('EnhanceParams — variant picker 過濾（family=realesrgan，跨 upscale/video_enhance）', () => {
  it('只列 realesrgan 家族；非 realesrgan 的 upscale 模型被排除', () => {
    modelsState.models = [
      { family: 'realesrgan', variant: 'x4plus', label: '4x', downloaded: true, category: 'upscale' },
      { family: 'swinir', variant: 'lightweight-x4', label: '4x lightweight', downloaded: true, category: 'upscale' },
      { family: 'realesrgan', variant: 'animevideov3', label: '4x video', downloaded: true, subcategory: 'video_enhance' },
    ]
    let captured: AgentCompositeField | null = null
    mountParams({ model: 'realesrgan', variant: 'x4plus' }, 'tool', null, (c) => { captured = c })
    expect(captured!.options().sort()).toEqual(['animevideov3', 'x4plus'])
  })
})

describe('EnhanceParams — composite（agent 欄位名沿舊 panel 用 model，實覆蓋 model+variant）', () => {
  it('註冊 composite：name=model, covers=[model,variant]', () => {
    let captured: AgentCompositeField | null = null
    mountParams({ model: 'realesrgan', variant: 'x4plus' }, 'tool', null, (c) => { captured = c })
    expect(captured!.name).toBe('model')
    expect(captured!.covers).toEqual(['model', 'variant'])
  })

  it('composite.get(params) 回 String(params.variant)（非 model）', () => {
    let captured: AgentCompositeField | null = null
    mountParams({ model: 'realesrgan', variant: 'x4plus' }, 'tool', null, (c) => { captured = c })
    expect(captured!.get({ model: 'realesrgan', variant: 'x2plus' })).toBe('x2plus')
  })

  it('composite.set(token) 回 {variant: token, model: "realesrgan"}', () => {
    let captured: AgentCompositeField | null = null
    mountParams({ model: 'realesrgan', variant: 'x4plus' }, 'tool', null, (c) => { captured = c })
    expect(captured!.set('animevideov3')).toEqual({ variant: 'animevideov3', model: 'realesrgan' })
  })

  it('選擇 variant picker → emit update:params 含 variant+model 兩欄', async () => {
    modelsState.models = [
      { family: 'realesrgan', variant: 'x4plus', label: '4x', downloaded: true, category: 'upscale' },
      { family: 'realesrgan', variant: 'x2plus', label: '2x', downloaded: true, category: 'upscale' },
    ]
    const w = mountParams({ model: 'realesrgan', variant: 'x4plus', output_format: 'mp4', video_codec: 'h264' })
    const select = w.findAllComponents(AppSelect)[0]
    await select.vm.$emit('update:modelValue', 'x2plus')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.variant).toBe('x2plus')
    expect(last.model).toBe('realesrgan')
  })
})

describe('EnhanceParams — 輸出解析度預覽', () => {
  it('variant 含 x2 → scale=2，預覽顯示 W×H → 2W×2H', () => {
    const w = mountParams({ model: 'realesrgan', variant: 'x2plus' }, 'tool', { width: 640, height: 480 })
    expect(w.text()).toContain('640×480 → 1280×960')
  })

  it('variant 不含 x2（x4plus 等）→ scale=4', () => {
    const w = mountParams({ model: 'realesrgan', variant: 'x4plus' }, 'tool', { width: 640, height: 480 })
    expect(w.text()).toContain('640×480 → 2560×1920')
  })

  it('無 fileInfo width/height → 不顯示解析度預覽區塊', () => {
    const w = mountParams({ model: 'realesrgan', variant: 'x4plus' }, 'tool', null)
    expect(w.find('.resolution-preview').exists()).toBe(false)
  })
})

describe('EnhanceParams — tool context：persisted seed（params.variant===defaults 時才套用）', () => {
  it('localStorage 有值且 params.variant===defaults.variant → 掛載時 seed patch', () => {
    localStorage.setItem('enhance_model', 'animevideov3')
    const w = mountParams({ model: 'realesrgan', variant: 'x4plus', output_format: 'mp4', video_codec: 'h264' })
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.variant).toBe('animevideov3')
    expect(last.model).toBe('realesrgan')
  })

  it('params.variant 已非 defaults → 不套用 seed', () => {
    localStorage.setItem('enhance_model', 'animevideov3')
    const w = mountParams({ model: 'realesrgan', variant: 'x2plus', output_format: 'mp4', video_codec: 'h264' })
    const emitted = w.emitted('update:params')
    if (emitted) {
      const last = emitted[emitted.length - 1][0] as Record<string, unknown>
      expect(last.variant).not.toBe('animevideov3')
    }
  })

  it('選擇模型後寫入 localStorage（tool context）', async () => {
    modelsState.models = [
      { family: 'realesrgan', variant: 'x4plus', label: '4x', downloaded: true, category: 'upscale' },
      { family: 'realesrgan', variant: 'x2plus', label: '2x', downloaded: true, category: 'upscale' },
    ]
    const w = mountParams({ model: 'realesrgan', variant: 'x4plus', output_format: 'mp4', video_codec: 'h264' })
    const select = w.findAllComponents(AppSelect)[0]
    await select.vm.$emit('update:modelValue', 'x2plus')
    expect(localStorage.getItem('enhance_model')).toBe('x2plus')
  })
})

describe('EnhanceParams — pipeline context：無 persisted seed', () => {
  it('pipeline context 掛載不套用 localStorage seed', () => {
    localStorage.setItem('enhance_model', 'animevideov3')
    const w = mountParams({ model: 'realesrgan', variant: 'x4plus', output_format: 'mp4', video_codec: 'h264' }, 'pipeline')
    const emitted = w.emitted('update:params')
    if (emitted) {
      const last = emitted[emitted.length - 1][0] as Record<string, unknown>
      expect(last.variant).not.toBe('animevideov3')
    }
  })

  it('pipeline context 選擇模型不寫入 localStorage', async () => {
    const w = mountParams({ model: 'realesrgan', variant: 'x4plus', output_format: 'mp4', video_codec: 'h264' }, 'pipeline')
    const select = w.findAllComponents(AppSelect)[0]
    await select.vm.$emit('update:modelValue', 'x2plus')
    expect(localStorage.getItem('enhance_model')).toBeNull()
  })
})
