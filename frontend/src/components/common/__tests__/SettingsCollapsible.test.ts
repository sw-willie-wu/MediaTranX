import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import SettingsCollapsible from '@/components/common/SettingsCollapsible.vue'

const mountOpts = { global: { mocks: { $t: (k: string) => k } } }

describe('SettingsCollapsible', () => {
  beforeEach(() => localStorage.clear())

  it('is collapsed by default — body hidden (v-show), chevron-right, aria-expanded false', () => {
    const w = mount(SettingsCollapsible, { ...mountOpts, props: { storageKey: 'test_advanced' } })
    expect(w.find('.settings-collapsible-body').exists()).toBe(true)
    expect(w.find('.settings-collapsible-body').isVisible()).toBe(false)
    expect(w.find('.bi-chevron-right').exists()).toBe(true)
    expect(w.find('button').attributes('aria-expanded')).toBe('false')
  })

  it('keeps slot content mounted when collapsed (v-show, not v-if)', () => {
    localStorage.clear()
    const w = mount(SettingsCollapsible, {
      props: { storageKey: 'test_w21_keep_mounted_advanced' },
      slots: { default: '<div class="probe">hi</div>' },
      global: { mocks: { $t: (k: string) => k } },
    })
    // default collapsed — slot still in DOM, but hidden via v-show
    expect(w.find('.probe').exists()).toBe(true)
    expect(w.find('.settings-collapsible-body').isVisible()).toBe(false)
  })

  it('expands on click — renders slot, persists true', async () => {
    const w = mount(SettingsCollapsible, {
      ...mountOpts,
      props: { storageKey: 'test_advanced' },
      slots: { default: '<p class="slotted">hi</p>' },
    })
    await w.find('button').trigger('click')
    expect(w.find('.settings-collapsible-body').exists()).toBe(true)
    expect(w.find('.slotted').exists()).toBe(true)
    expect(w.find('button').attributes('aria-expanded')).toBe('true')
    expect(localStorage.getItem('test_advanced')).toBe('true')
  })

  it('restores open state from localStorage on mount', () => {
    localStorage.setItem('persisted_advanced', 'true')
    const w = mount(SettingsCollapsible, { ...mountOpts, props: { storageKey: 'persisted_advanced' } })
    expect(w.find('.settings-collapsible-body').exists()).toBe(true)
  })

  it('uses custom title when provided', () => {
    const w = mount(SettingsCollapsible, { ...mountOpts, props: { storageKey: 'k', title: 'Custom' } })
    expect(w.find('.settings-collapsible-header').text()).toContain('Custom')
  })
})
