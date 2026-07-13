/**
 * UpscaleParams.vue 單測（統一參數元件案批 4 Task 4.4）。
 * 覆蓋：掛載載入模型清單、雙 composite（upscale_model/face_restore_model）覆蓋欄位/token
 * 映射、maxScale 動態夾、face_fix 顯隱、tool/pipeline context persisted seed 分流。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import type { AgentCompositeField } from '../../types'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

interface FakeModel {
  id: string
  family: string
  variant: string
  label: string
  downloaded: boolean
  category?: string
  max_scale?: number
}

const modelsState = vi.hoisted(() => ({ models: [] as FakeModel[] }))
const ensureLoadedMock = vi.hoisted(() => vi.fn())
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({
    loading: false,
    byCategory: (cat: string) => modelsState.models.filter((m) => m.category === cat),
    forPanel: (items: unknown[]) => items,
    ensureLoaded: ensureLoadedMock,
  }),
}))

import UpscaleParams from '../UpscaleParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'

function mountParams(
  params: Record<string, unknown>,
  context: 'tool' | 'pipeline' = 'tool',
  fileInfo: Record<string, unknown> | null = null,
  onRegister?: (c: AgentCompositeField) => void,
) {
  return mount(UpscaleParams, {
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

const DEFAULTS = { model_id: 'realesrgan-x4plus', scale: 4, sharpen: false, face_fix: false, face_restore_upscale: 2 }

beforeEach(() => {
  modelsState.models = []
  localStorage.clear()
  ensureLoadedMock.mockClear()
})

describe('UpscaleParams — 掛載時載入模型清單', () => {
  it('mount 後 modelStore.ensureLoaded 被呼叫', () => {
    mountParams(DEFAULTS)
    expect(ensureLoadedMock).toHaveBeenCalledTimes(1)
  })
})

describe('UpscaleParams — 雙 composite 註冊', () => {
  it('註冊兩個 composite：upscale_model(covers model_id) + face_restore_model(covers face_restore_model_id)', () => {
    const captured: AgentCompositeField[] = []
    mountParams(DEFAULTS, 'tool', null, (c) => captured.push(c))
    expect(captured.map((c) => c.name)).toEqual(['upscale_model', 'face_restore_model'])
    expect(captured[0].covers).toEqual(['model_id'])
    expect(captured[1].covers).toEqual(['face_restore_model_id'])
  })

  it('upscale_model composite get/set 直接映射 model_id（無 encode/decode）', () => {
    const captured: AgentCompositeField[] = []
    mountParams(DEFAULTS, 'tool', null, (c) => captured.push(c))
    const upscaleComposite = captured[0]
    expect(upscaleComposite.get({ model_id: 'swinir-lightweight-x4' })).toBe('swinir-lightweight-x4')
    expect(upscaleComposite.set('swinir-lightweight-x4')).toEqual({ model_id: 'swinir-lightweight-x4' })
  })

  it('face_restore_model composite get/set 直接映射 face_restore_model_id', () => {
    const captured: AgentCompositeField[] = []
    mountParams(DEFAULTS, 'tool', null, (c) => captured.push(c))
    const faceComposite = captured[1]
    expect(faceComposite.get({ face_restore_model_id: 'gfpgan-v1.4' })).toBe('gfpgan-v1.4')
    expect(faceComposite.set('gfpgan-v1.4')).toEqual({ face_restore_model_id: 'gfpgan-v1.4' })
  })

  it('composite.options() 反映 upscaleModels/faceRestoreModels 清單', () => {
    modelsState.models = [
      { id: 'realesrgan-x4plus', family: 'realesrgan', variant: 'x4plus', label: '4x', downloaded: true, category: 'upscale' },
      { id: 'gfpgan-v1.4', family: 'gfpgan', variant: 'v1.4', label: 'v1.4', downloaded: true, category: 'face_restore' },
    ]
    const captured: AgentCompositeField[] = []
    mountParams(DEFAULTS, 'tool', null, (c) => captured.push(c))
    expect(captured[0].options()).toEqual(['realesrgan-x4plus'])
    expect(captured[1].options()).toEqual(['gfpgan-v1.4'])
  })
})

describe('UpscaleParams — 選擇模型 → emit update:params', () => {
  it('選擇主模型 → commitPatch({model_id})', async () => {
    modelsState.models = [
      { id: 'realesrgan-x4plus', family: 'realesrgan', variant: 'x4plus', label: '4x', downloaded: true, category: 'upscale' },
      { id: 'swinir-lightweight-x4', family: 'swinir', variant: 'lightweight-x4', label: 'SwinIR', downloaded: true, category: 'upscale' },
    ]
    const w = mountParams(DEFAULTS)
    const select = w.findAllComponents(AppSelect)[0]
    await select.vm.$emit('update:modelValue', 'swinir-lightweight-x4')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.model_id).toBe('swinir-lightweight-x4')
  })
})

describe('UpscaleParams — maxScale 動態夾', () => {
  it('選中模型 max_scale=2 且 params.scale=4 → 夾回 2', async () => {
    modelsState.models = [
      { id: 'realesrgan-x2plus', family: 'realesrgan', variant: 'x2plus', label: '2x', downloaded: true, category: 'upscale', max_scale: 2 },
    ]
    const w = mountParams({ ...DEFAULTS, model_id: 'realesrgan-x2plus', scale: 4 })
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.scale).toBe(2)
  })

  it('選中模型 max_scale=4 且 params.scale=4 → 不觸發 patch', () => {
    modelsState.models = [
      { id: 'realesrgan-x4plus', family: 'realesrgan', variant: 'x4plus', label: '4x', downloaded: true, category: 'upscale', max_scale: 4 },
    ]
    const w = mountParams(DEFAULTS)
    expect(w.emitted('update:params')).toBeFalsy()
  })

  it('AppRange :max 綁 maxScale', () => {
    modelsState.models = [
      { id: 'realesrgan-x2plus', family: 'realesrgan', variant: 'x2plus', label: '2x', downloaded: true, category: 'upscale', max_scale: 2 },
    ]
    const w = mountParams({ ...DEFAULTS, model_id: 'realesrgan-x2plus', scale: 2 })
    const range = w.findAllComponents(AppRange)[0]
    expect(range.props('max')).toBe(2)
  })
})

describe('UpscaleParams — face_fix 顯隱', () => {
  it('face_fix=false → 不顯示 sub-params 區塊', () => {
    const w = mountParams(DEFAULTS)
    expect(w.find('.sub-params').exists()).toBe(false)
  })

  it('face_fix=true → 顯示 sub-params（face model picker）', () => {
    const w = mountParams({ ...DEFAULTS, face_fix: true })
    expect(w.find('.sub-params').exists()).toBe(true)
  })

  it('face_fix=true 且選中模型非 gfpgan 家族 → 不顯示 face_restore_upscale 滑桿', () => {
    const w = mountParams({ ...DEFAULTS, face_fix: true, face_restore_model_id: 'some-other-model' })
    expect(w.findAllComponents(AppRange)).toHaveLength(1) // 只剩主 scale slider
  })

  it('face_fix=true 且選中 gfpgan 家族模型 → 顯示 face_restore_upscale 滑桿', () => {
    const w = mountParams({ ...DEFAULTS, face_fix: true, face_restore_model_id: 'gfpgan-v1.4' })
    expect(w.findAllComponents(AppRange)).toHaveLength(2)
  })
})

describe('UpscaleParams — tool context：persisted seed', () => {
  it('localStorage 有值且 model_id===defaults → 掛載時 seed patch', () => {
    localStorage.setItem('upscale_model', 'swinir-lightweight-x4')
    const w = mountParams(DEFAULTS)
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.model_id).toBe('swinir-lightweight-x4')
  })

  it('face model：localStorage 有值且目前無 face_restore_model_id → 掛載時 seed', () => {
    localStorage.setItem('upscale_face_model', 'gfpgan-v1.4')
    const w = mountParams(DEFAULTS)
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.face_restore_model_id).toBe('gfpgan-v1.4')
  })

  it('upscale_model 與 upscale_face_model 同時持久化 → 掛載後兩者皆保留（雙 seed 互踩回歸測試）', () => {
    localStorage.setItem('upscale_model', 'swinir-lightweight-x4')
    localStorage.setItem('upscale_face_model', 'gfpgan-v1.4')
    const w = mountParams(DEFAULTS)
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.model_id).toBe('swinir-lightweight-x4')
    expect(last.face_restore_model_id).toBe('gfpgan-v1.4')
  })

  it('選擇模型後寫入 localStorage（tool context）', async () => {
    modelsState.models = [
      { id: 'realesrgan-x4plus', family: 'realesrgan', variant: 'x4plus', label: '4x', downloaded: true, category: 'upscale' },
      { id: 'swinir-lightweight-x4', family: 'swinir', variant: 'lightweight-x4', label: 'SwinIR', downloaded: true, category: 'upscale' },
    ]
    const w = mountParams(DEFAULTS)
    const select = w.findAllComponents(AppSelect)[0]
    await select.vm.$emit('update:modelValue', 'swinir-lightweight-x4')
    expect(localStorage.getItem('upscale_model')).toBe('swinir-lightweight-x4')
  })
})

describe('UpscaleParams — pipeline context：無 persisted seed', () => {
  it('pipeline context 掛載不套用 localStorage seed', () => {
    localStorage.setItem('upscale_model', 'swinir-lightweight-x4')
    const w = mountParams(DEFAULTS, 'pipeline')
    const emitted = w.emitted('update:params')
    if (emitted) {
      const last = emitted[emitted.length - 1][0] as Record<string, unknown>
      expect(last.model_id).not.toBe('swinir-lightweight-x4')
    }
  })

  it('pipeline context 選擇模型不寫入 localStorage', async () => {
    const w = mountParams(DEFAULTS, 'pipeline')
    const select = w.findAllComponents(AppSelect)[0]
    await select.vm.$emit('update:modelValue', 'swinir-lightweight-x4')
    expect(localStorage.getItem('upscale_model')).toBeNull()
  })
})
