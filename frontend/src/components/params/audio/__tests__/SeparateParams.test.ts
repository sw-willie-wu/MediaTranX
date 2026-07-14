/**
 * SeparateParams.vue 單測（統一參數元件 spec §5；批 3 Task 3.3）。
 * 覆蓋：6 stem toggle 響應式衍生（undefined=全選、陣列=顯式）、toggle 雙向寫回完整陣列
 * （即使全選也不寫回 undefined）、output_format/generate_midi 直寫。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

// AppSelect.vue 內部呼叫 useI18n()（非僅靠父層 $t mock）——沿 InterpolateParams.test.ts 先例
// 全域 mock，否則掛載時無 vue-i18n 外掛會丟 SyntaxError: Need to install with `app.use`。
vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import SeparateParams from '../SeparateParams.vue'
import AppToggle from '@/components/common/AppToggle.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import { hasParamComponent, METAS } from '../../index'

function mockT(k: string): string {
  return k
}

function mountParams(params: Record<string, unknown>, context: 'tool' | 'pipeline' = 'tool') {
  return mount(SeparateParams, {
    props: { params, context, fileInfo: null },
    global: {
      mocks: { $t: mockT },
    },
  })
}

const STEM_NAMES = ['vocals', 'drums', 'bass', 'guitar', 'piano', 'other']

describe('SeparateParams — stems 響應式衍生（undefined=全選）', () => {
  it('params.stems 未設 → 6 個 toggle 全部 on', () => {
    const w = mountParams({})
    const toggles = w.findAllComponents(AppToggle)
    // 前 6 個是 stem toggle，第 7 個是 generate_midi
    for (let i = 0; i < 6; i++) {
      expect(toggles[i].props('modelValue')).toBe(true)
    }
  })

  it('params.stems=["vocals","drums"] → 只有這兩個 toggle on，其餘 off', () => {
    const w = mountParams({ stems: ['vocals', 'drums'] })
    const toggles = w.findAllComponents(AppToggle)
    STEM_NAMES.forEach((name, i) => {
      expect(toggles[i].props('modelValue')).toBe(['vocals', 'drums'].includes(name))
    })
  })

  it('params.stems=[]（空陣列）→ 全部 toggle off', () => {
    const w = mountParams({ stems: [] })
    const toggles = w.findAllComponents(AppToggle)
    for (let i = 0; i < 6; i++) {
      expect(toggles[i].props('modelValue')).toBe(false)
    }
  })
})

describe('SeparateParams — toggle 變更一律寫回完整陣列（不寫回 undefined）', () => {
  it('undefined（全選）→ 關掉 vocals → emit stems=[drums,bass,guitar,piano,other]（保留其餘 5 個，全列陣列非 undefined）', async () => {
    const w = mountParams({})
    const toggles = w.findAllComponents(AppToggle)
    await toggles[0].vm.$emit('update:modelValue', false) // vocals off

    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.stems).toEqual(['drums', 'bass', 'guitar', 'piano', 'other'])
  })

  it('已是顯式陣列 → 重新勾選一個 stem → 寫回新的完整陣列', async () => {
    const w = mountParams({ stems: ['vocals'] })
    const toggles = w.findAllComponents(AppToggle)
    await toggles[1].vm.$emit('update:modelValue', true) // drums on

    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.stems).toEqual(['vocals', 'drums'])
  })

  it('全選時點回全部 6 個 → 寫回完整 6 項陣列（不是 undefined，設計定案）', async () => {
    const w = mountParams({ stems: ['vocals'] })
    // 依序把其餘 5 個都打開——每次都把上一次 emit 的結果經 setProps 回灌（模擬 host 收斂 params
    // 後把新值傳回元件的真實迴路；元件本身不持有本地 truth，見檔頭註解）。
    for (let i = 1; i < 6; i++) {
      const toggles = w.findAllComponents(AppToggle)
      await toggles[i].vm.$emit('update:modelValue', true)
      const emitted = w.emitted('update:params')!
      const patch = emitted[emitted.length - 1][0] as Record<string, unknown>
      await w.setProps({ params: patch })
    }
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.stems).toEqual(['vocals', 'drums', 'bass', 'guitar', 'piano', 'other'])
    expect(last.stems).not.toBeUndefined()
  })
})

describe('SeparateParams — output_format / generate_midi 直寫', () => {
  it('AppSelect 顯示 output_format（default wav）', () => {
    const w = mountParams({})
    const select = w.findComponent(AppSelect)
    expect(select.props('modelValue')).toBe('wav')
  })

  it('切換 output_format → emit update:params 含新值（stems/generate_midi 保留原值）', async () => {
    const w = mountParams({ generate_midi: true })
    const select = w.findComponent(AppSelect)
    await select.vm.$emit('update:modelValue', 'flac')

    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.output_format).toBe('flac')
    expect(last.generate_midi).toBe(true)
  })

  it('generate_midi toggle（第 7 個 AppToggle）→ emit 新布林值', async () => {
    const w = mountParams({})
    const toggles = w.findAllComponents(AppToggle)
    expect(toggles).toHaveLength(7)
    await toggles[6].vm.$emit('update:modelValue', true)

    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.generate_midi).toBe(true)
  })
})

describe('params/index.ts 載入表', () => {
  it('hasParamComponent("audio.separate") === true', () => {
    expect(hasParamComponent('audio.separate')).toBe(true)
  })

  it('METAS["audio.separate"].toolKey === "audio.separate"', () => {
    expect(METAS['audio.separate'].toolKey).toBe('audio.separate')
  })
})
