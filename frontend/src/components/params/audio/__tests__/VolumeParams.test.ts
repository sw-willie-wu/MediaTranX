/**
 * VolumeParams.vue 單測（統一參數元件 spec §5；批 3 Task 3.1）。
 * 覆蓋：mode 響應式衍生（切換 normalize 歸零 volume_db）、AppRange 滑桿 ±20、
 * gainPreview emit（10^(db/20)，normalize 恆 1）。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import VolumeParams from '../VolumeParams.vue'
import AppRange from '@/components/common/AppRange.vue'
import { hasParamComponent, METAS } from '../../index'

function mockT(k: string): string {
  return k
}

function mountParams(params: Record<string, unknown>, context: 'tool' | 'pipeline' = 'tool') {
  return mount(VolumeParams, {
    props: { params, context, fileInfo: null },
    global: {
      mocks: { $t: mockT },
    },
  })
}

describe('VolumeParams — mode 響應式衍生（params.normalize 反推）', () => {
  it('normalize=false（或未設）→ mode=adjust，滑桿顯示', () => {
    const w = mountParams({ volume_db: 5, normalize: false })
    expect(w.find('.btn-choice.is-active').text()).toBe('audio.volume.manual')
    expect(w.findComponent(AppRange).exists()).toBe(true)
  })

  it('normalize=true → mode=normalize，滑桿隱藏、顯示 hint', () => {
    const w = mountParams({ volume_db: 0, normalize: true })
    expect(w.find('.btn-choice.is-active').text()).toBe('audio.volume.normalize')
    expect(w.findComponent(AppRange).exists()).toBe(false)
    expect(w.text()).toContain('audio.volume.normalize_hint')
  })
})

describe('VolumeParams — 模式切換保留 volume_db（歸零由 buildSubmit 在送出時處理）', () => {
  it('adjust(volume_db=12) → 點 normalize 按鈕 → emit {normalize:true}，volume_db 保留 12', async () => {
    const w = mountParams({ volume_db: 12, normalize: false })
    const buttons = w.findAll('.btn-choice')
    await buttons[1].trigger('click') // normalize 按鈕

    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toEqual({ volume_db: 12, normalize: true })
  })

  it('normalize → 點 adjust 按鈕 → emit {normalize:false}（volume_db 不強制寫回，維持既有 params 值）', async () => {
    const w = mountParams({ volume_db: 0, normalize: true })
    const buttons = w.findAll('.btn-choice')
    await buttons[0].trigger('click') // adjust 按鈕

    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toEqual({ volume_db: 0, normalize: false })
  })
})

describe('VolumeParams — AppRange 滑桿 ±20（UI 收斂，schema 容 ±30）', () => {
  it('min/max 屬性為 -20/20', () => {
    const w = mountParams({ volume_db: 0, normalize: false })
    const range = w.findComponent(AppRange)
    expect(range.props('min')).toBe(-20)
    expect(range.props('max')).toBe(20)
  })

  it('拖曳滑桿 → emit update:params 含新 volume_db', async () => {
    const w = mountParams({ volume_db: 0, normalize: false })
    const range = w.findComponent(AppRange)
    range.vm.$emit('update:modelValue', 8)
    await w.vm.$nextTick()

    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toEqual({ volume_db: 8, normalize: false })
  })
})

describe('VolumeParams — gainPreview 出向（10^(db/20)，沿 CropParams $attrs/emit 先例）', () => {
  it('掛載即 emit update:gainPreview（immediate，依初始 volume_db）', () => {
    const w = mountParams({ volume_db: 20, normalize: false })
    const emitted = w.emitted('update:gainPreview')!
    expect(emitted[0][0]).toBeCloseTo(10, 5) // 10^(20/20) = 10
  })

  it('volume_db=0 → gain=1', () => {
    const w = mountParams({ volume_db: 0, normalize: false })
    const emitted = w.emitted('update:gainPreview')!
    expect(emitted[emitted.length - 1][0]).toBeCloseTo(1, 5)
  })

  it('拖曳滑桿改變 volume_db（經 props 回灌）→ gain 重新計算', async () => {
    const w = mountParams({ volume_db: 0, normalize: false })
    await w.setProps({ params: { volume_db: -20, normalize: false } })

    const emitted = w.emitted('update:gainPreview')!
    expect(emitted[emitted.length - 1][0]).toBeCloseTo(0.1, 5) // 10^(-20/20) = 0.1
  })

  it('normalize 模式 → gain 恆為 1（不論 volume_db 值）', async () => {
    const w = mountParams({ volume_db: 15, normalize: true })
    const emitted = w.emitted('update:gainPreview')!
    expect(emitted[emitted.length - 1][0]).toBe(1)
  })
})

describe('params/index.ts 載入表', () => {
  it('hasParamComponent("audio.volume") === true', () => {
    expect(hasParamComponent('audio.volume')).toBe(true)
  })

  it('METAS["audio.volume"].toolKey === "audio.volume"', () => {
    expect(METAS['audio.volume'].toolKey).toBe('audio.volume')
  })
})
