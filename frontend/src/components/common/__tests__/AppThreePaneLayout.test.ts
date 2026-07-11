import { describe, it, expect, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import AppThreePaneLayout from '@/components/common/AppThreePaneLayout.vue'
import { useResizableLayout, DEFAULTS } from '@/composables/useResizableLayout'

// useResizableLayout 是 module-level singleton；在測試頂層呼叫會有
// onBeforeUnmount outside-setup 的 dev warning，無害、僅為取得共享 refs。
const slots = {
  left: '<div class="probe-left">L</div>',
  center: '<div class="probe-center">C</div>',
  right: '<div class="probe-right">R</div>',
}

describe('AppThreePaneLayout', () => {
  beforeEach(() => {
    localStorage.clear()
    const { sidebarWidth, settingsWidth } = useResizableLayout()
    sidebarWidth.value = DEFAULTS.sidebar
    settingsWidth.value = DEFAULTS.settings
  })

  it('renders three slots inside tp-left / tp-center / tp-right', () => {
    const w = mount(AppThreePaneLayout, { slots })
    expect(w.find('.tp-left .probe-left').exists()).toBe(true)
    expect(w.find('.tp-center .probe-center').exists()).toBe(true)
    expect(w.find('.tp-right .probe-right').exists()).toBe(true)
  })

  it('binds singleton widths to left/right pane styles (reactive)', async () => {
    const { sidebarWidth, settingsWidth } = useResizableLayout()
    const w = mount(AppThreePaneLayout, { slots })
    // 完整比對 width + min-width，避免 'width: X' substring 被 'min-width: X' 掩蓋
    expect(w.find('.tp-left').attributes('style')).toBe(`width: ${DEFAULTS.sidebar}px; min-width: ${DEFAULTS.sidebar}px;`)
    expect(w.find('.tp-right').attributes('style')).toBe(`width: ${DEFAULTS.settings}px; min-width: ${DEFAULTS.settings}px;`)
    sidebarWidth.value = 260
    settingsWidth.value = 300
    await nextTick()
    expect(w.find('.tp-left').attributes('style')).toBe('width: 260px; min-width: 260px;')
    expect(w.find('.tp-right').attributes('style')).toBe('width: 300px; min-width: 300px;')
  })

  it('passes leftClass / centerClass / rightClass through to pane elements', () => {
    const w = mount(AppThreePaneLayout, {
      slots,
      props: { leftClass: 'aa', centerClass: { 'is-drag-over': true }, rightClass: 'cc' },
    })
    expect(w.find('.tp-left').classes()).toContain('aa')
    expect(w.find('.tp-center').classes()).toContain('is-drag-over')
    expect(w.find('.tp-right').classes()).toContain('cc')
  })

  it('dblclick on handles resets widths to DEFAULTS without touching localStorage', async () => {
    const { sidebarWidth, settingsWidth } = useResizableLayout()
    sidebarWidth.value = 280
    settingsWidth.value = 400
    const w = mount(AppThreePaneLayout, { slots })
    const handles = w.findAll('.resize-handle')
    expect(handles).toHaveLength(2)
    await handles[0].trigger('dblclick')
    await handles[1].trigger('dblclick')
    expect(sidebarWidth.value).toBe(DEFAULTS.sidebar)
    expect(settingsWidth.value).toBe(DEFAULTS.settings)
    expect(localStorage.getItem('tool-layout-widths')).toBeNull()
  })
})
