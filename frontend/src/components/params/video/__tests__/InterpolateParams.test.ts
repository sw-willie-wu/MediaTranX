/**
 * InterpolateParams.vue 單測（統一參數元件案批 2 Task 2.3）。
 * 覆蓋：掛載載入模型清單、custom 模式顯示 target_fps、composite set 寫回 model 欄位、
 * tool/pipeline context 的 persisted seed 分流。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import type { AgentCompositeField } from '../../types'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

const modelsState = vi.hoisted(() => ({
  models: [] as Array<{ family: string; variant: string; label: string; downloaded: boolean; category?: string }>,
}))
const ensureLoadedMock = vi.hoisted(() => vi.fn())
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    byCategory: (cat: string) => modelsState.models.filter((m) => m.category === cat),
    forPanel: (items: unknown[]) => items,
    ensureLoaded: ensureLoadedMock,
  }),
}))

import InterpolateParams from '../InterpolateParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'

function mountParams(
  params: Record<string, unknown>,
  context: 'tool' | 'pipeline' = 'tool',
  fileInfo: Record<string, unknown> | null = null,
  onRegister?: (c: AgentCompositeField) => void,
) {
  return mount(InterpolateParams, {
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

describe('InterpolateParams — 掛載時載入模型清單', () => {
  it('mount 後 modelStore.ensureLoaded 被呼叫', () => {
    mountParams({ model: 'v4.26', mode: '2x', output_format: 'mp4', video_codec: 'h264' })
    expect(ensureLoadedMock).toHaveBeenCalledTimes(1)
  })
})

describe('InterpolateParams — 佈局（沿舊 panel 分組）', () => {
  it('mode=2x：target_fps 不顯示，video_codec 在 SettingsCollapsible 內', () => {
    const w = mountParams({ model: 'v4.26', mode: '2x', output_format: 'mp4', video_codec: 'h264' })
    expect(w.findComponent(AppRange).exists()).toBe(false)
    expect(w.find('.settings-collapsible').exists()).toBe(true)
  })

  it('mode=custom：target_fps（AppRange）顯示', () => {
    const w = mountParams({ model: 'v4.26', mode: 'custom', target_fps: 90, output_format: 'mp4', video_codec: 'h264' })
    expect(w.findComponent(AppRange).exists()).toBe(true)
    expect(w.findComponent(AppRange).props('modelValue')).toBe(90)
  })

  it('mode=custom 且 targetFps <= sourceFps → 顯示 fps_warning 提示', () => {
    const w = mountParams(
      { model: 'v4.26', mode: 'custom', target_fps: 20, output_format: 'mp4', video_codec: 'h264' },
      'tool',
      { fps: 30 },
    )
    expect(w.text()).toContain('video.interpolate.fps_warning')
  })

  it('mode=custom 且 targetFps > sourceFps → 不顯示 fps_warning', () => {
    const w = mountParams(
      { model: 'v4.26', mode: 'custom', target_fps: 90, output_format: 'mp4', video_codec: 'h264' },
      'tool',
      { fps: 30 },
    )
    expect(w.text()).not.toContain('video.interpolate.fps_warning')
  })

  it('拖動 target_fps → commitPatch target_fps', async () => {
    const w = mountParams({ model: 'v4.26', mode: 'custom', target_fps: 90, output_format: 'mp4', video_codec: 'h264' })
    await w.findComponent(AppRange).vm.$emit('update:modelValue', 120)
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.target_fps).toBe(120)
  })
})

describe('InterpolateParams — model picker composite', () => {
  it('註冊 composite：name=model, covers=[model]', () => {
    let captured: AgentCompositeField | null = null
    mountParams({ model: 'v4.26', mode: '2x', output_format: 'mp4', video_codec: 'h264' }, 'tool', null, (c) => { captured = c })
    expect(captured).toBeTruthy()
    expect(captured!.name).toBe('model')
    expect(captured!.covers).toEqual(['model'])
  })

  it('composite.get(params) 回 String(params.model)', () => {
    let captured: AgentCompositeField | null = null
    mountParams({ model: 'v4.26', mode: '2x' }, 'tool', null, (c) => { captured = c })
    expect(captured!.get({ model: 'v4.26' })).toBe('v4.26')
  })

  it('composite.set(token) 回 {model: token}', () => {
    let captured: AgentCompositeField | null = null
    mountParams({ model: 'v4.26', mode: '2x' }, 'tool', null, (c) => { captured = c })
    expect(captured!.set('v4.30')).toEqual({ model: 'v4.30' })
  })

  it('composite.options() 反映即時 modelStore 清單（token 陣列）', () => {
    modelsState.models = [
      { family: 'rife', variant: 'v4.26', label: 'v4.26', downloaded: true, category: 'interpolate' },
    ]
    let captured: AgentCompositeField | null = null
    mountParams({ model: 'v4.26', mode: '2x' }, 'tool', null, (c) => { captured = c })
    expect(captured!.options()).toEqual(['v4.26'])
  })

  it('選擇 model picker → emit update:params 含新 model 值', async () => {
    modelsState.models = [
      { family: 'rife', variant: 'v4.26', label: 'v4.26', downloaded: true, category: 'interpolate' },
    ]
    const w = mountParams({ model: 'v4.26', mode: '2x', output_format: 'mp4', video_codec: 'h264' })
    const select = w.findAllComponents(AppSelect)[0]
    await select.vm.$emit('update:modelValue', 'v4.30')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.model).toBe('v4.30')
  })
})

describe('InterpolateParams — tool context：persisted seed（params 等於 defaults 時才套用）', () => {
  it('localStorage 有值且 params.model===defaults.model → 掛載時 seed patch', () => {
    localStorage.setItem('interpolate_model', 'v4.30')
    const w = mountParams({ model: 'v4.26', mode: '2x', output_format: 'mp4', video_codec: 'h264' })
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.model).toBe('v4.30')
  })

  it('params.model 已非 defaults → 不套用 seed', () => {
    localStorage.setItem('interpolate_model', 'v4.30')
    const w = mountParams({ model: 'custom-variant', mode: '2x', output_format: 'mp4', video_codec: 'h264' })
    const emitted = w.emitted('update:params')
    if (emitted) {
      const last = emitted[emitted.length - 1][0] as Record<string, unknown>
      expect(last.model).not.toBe('v4.30')
    }
  })

  it('選擇模型後寫入 localStorage（tool context）', async () => {
    const w = mountParams({ model: 'v4.26', mode: '2x', output_format: 'mp4', video_codec: 'h264' })
    const select = w.findAllComponents(AppSelect)[0]
    await select.vm.$emit('update:modelValue', 'v4.30')
    expect(localStorage.getItem('interpolate_model')).toBe('v4.30')
  })
})

describe('InterpolateParams — pipeline context：無 persisted seed', () => {
  it('pipeline context 掛載不套用 localStorage seed', () => {
    localStorage.setItem('interpolate_model', 'v4.30')
    const w = mountParams({ model: 'v4.26', mode: '2x', output_format: 'mp4', video_codec: 'h264' }, 'pipeline')
    const emitted = w.emitted('update:params')
    if (emitted) {
      const last = emitted[emitted.length - 1][0] as Record<string, unknown>
      expect(last.model).not.toBe('v4.30')
    }
  })

  it('pipeline context 選擇模型不寫入 localStorage', async () => {
    const w = mountParams({ model: 'v4.26', mode: '2x', output_format: 'mp4', video_codec: 'h264' }, 'pipeline')
    const select = w.findAllComponents(AppSelect)[0]
    await select.vm.$emit('update:modelValue', 'v4.30')
    expect(localStorage.getItem('interpolate_model')).toBeNull()
  })
})

