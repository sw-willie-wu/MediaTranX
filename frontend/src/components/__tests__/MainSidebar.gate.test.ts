import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/' }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('vue-i18n', async (orig) => {
  const mod = await orig<typeof import('vue-i18n')>()
  return { ...mod, useI18n: () => ({ t: (k: string) => k }) }
})

import MainSidebar from '@/components/MainSidebar.vue'

const w = window as unknown as { electron?: { updateChannel?: string | null } }

function mountSidebar() {
  setActivePinia(createPinia())
  return mount(MainSidebar, { global: { mocks: { $t: (k: string) => k } } })
}

afterEach(() => { delete w.electron })

describe('MainSidebar — pipeline gate', () => {
  // 注意：nav label 只渲染在 data-tooltip 屬性＋CSS ::after，不進 textContent——
  // 必須用屬性 selector 斷言，wrap.text() 會 dev 案例必紅、stable 案例假綠。
  it('stable：無流程項', () => {
    w.electron = { updateChannel: 'stable' }
    const wrap = mountSidebar()
    expect(wrap.find('[data-tooltip="nav.pipeline"]').exists()).toBe(false)
    expect(wrap.find('[data-tooltip="nav.image"]').exists()).toBe(true) // 其餘項健在
  })
  it('dev（jsdom 缺省無 electron）：有流程項', () => {
    const wrap = mountSidebar()
    expect(wrap.find('[data-tooltip="nav.pipeline"]').exists()).toBe(true)
  })
})
