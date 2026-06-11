// @vitest-environment jsdom
/**
 * Backdrop + running-banner behaviour for the chat bubble.
 *
 * - Expanded: a full-screen backdrop blocks the app; clicking it collapses.
 * - Running: the backdrop stays (even after collapse) so the user can't fight
 *   the agent for panel state mid-run, and a fixed top banner shows progress
 *   with a square stop button that aborts the run.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia, type Pinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en'
import ChatBubble from '@/components/agent/ChatBubble.vue'
import { bubbleVisible, bubbleExpanded } from '@/composables/useBubbleVisibility'
import { useAgent, _resetAgent } from '@/composables/useAgent'
import { useAgentStore } from '@/stores/agent'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

let pinia: Pinia

// Single shared pinia so the test and the mounted component see the SAME stores
// (a separate createPinia() in the plugin list would desync store.isRunning).
function mountBubble() {
  return mount(ChatBubble, {
    attachTo: document.body,
    global: { plugins: [pinia, i18n] },
  })
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  _resetAgent()
  bubbleVisible.value = true
  bubbleExpanded.value = false
})

afterEach(() => {
  bubbleVisible.value = false
  bubbleExpanded.value = false
  document.body.innerHTML = ''
})

describe('ChatBubble backdrop', () => {
  it('renders no backdrop while collapsed and idle', () => {
    const w = mountBubble()
    expect(document.body.querySelector('.chat-bubble-backdrop')).toBeNull()
    w.unmount()
  })

  it('renders a full-screen backdrop when expanded', async () => {
    const w = mountBubble()
    bubbleExpanded.value = true
    await w.vm.$nextTick()
    expect(document.body.querySelector('.chat-bubble-backdrop')).not.toBeNull()
    w.unmount()
  })

  it('collapses the panel when the backdrop is clicked (idle)', async () => {
    const w = mountBubble()
    bubbleExpanded.value = true
    await w.vm.$nextTick()

    const backdrop = document.body.querySelector('.chat-bubble-backdrop') as HTMLElement
    expect(backdrop).not.toBeNull()
    backdrop.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await w.vm.$nextTick()

    expect(bubbleExpanded.value).toBe(false)
    expect(document.body.querySelector('.chat-bubble-backdrop')).toBeNull()
    w.unmount()
  })
})

describe('ChatBubble running banner', () => {
  it('keeps the backdrop + shows the banner while running, even when collapsed', async () => {
    const store = useAgentStore()
    const w = mountBubble()
    store.start() // isRunning = true
    bubbleExpanded.value = false
    await w.vm.$nextTick()

    expect(document.body.querySelector('.chat-bubble-backdrop')).not.toBeNull()
    const banner = document.body.querySelector('.agent-running-banner')
    expect(banner).not.toBeNull()
    expect(banner!.textContent).toContain('Thinking')
    expect(document.body.querySelector('.banner-stop')).not.toBeNull()
    w.unmount()
  })

  it('shows the live action label in the banner once a tool dispatches', async () => {
    const store = useAgentStore()
    const w = mountBubble()
    store.start() // fresh store → currentAction empty → thinking label
    await w.vm.$nextTick()
    expect(document.body.querySelector('.banner-label')!.textContent).toContain('Thinking')

    // A tool dispatch sets the current action; banner reflects it live.
    store.setCurrentAction('agent.banner.act.set_field', { field: 'model', value: 'qwen3:8b' })
    await w.vm.$nextTick()
    expect(document.body.querySelector('.banner-label')!.textContent).toContain('Setting model = qwen3:8b')
    w.unmount()
  })

  it('localizes navigate_to route to the domain name (not the raw /route)', async () => {
    const store = useAgentStore()
    const w = mountBubble()
    store.start()
    store.setCurrentAction('agent.banner.act.navigate_to', { route: '/video' })
    await w.vm.$nextTick()
    const text = document.body.querySelector('.banner-label')!.textContent!
    expect(text).toContain('Video Tools') // nav.video, not "/video"
    expect(text).not.toContain('/video')
    w.unmount()
  })

  it('hides the banner while running when the chat is expanded (panel shows progress)', async () => {
    const store = useAgentStore()
    const w = mountBubble()
    store.start()
    bubbleExpanded.value = true
    await w.vm.$nextTick()
    expect(document.body.querySelector('.agent-running-banner')).toBeNull()
    // backdrop is still present (dim scrim, not the transparent is-watch variant)
    const backdrop = document.body.querySelector('.chat-bubble-backdrop')
    expect(backdrop).not.toBeNull()
    expect(backdrop!.classList.contains('is-watch')).toBe(false)
    w.unmount()
  })

  it('hides the banner when not running', async () => {
    const store = useAgentStore()
    const w = mountBubble()
    store.stop()
    await w.vm.$nextTick()
    expect(document.body.querySelector('.agent-running-banner')).toBeNull()
    w.unmount()
  })

  it('stop button aborts the run via cancelRun', async () => {
    const agent = useAgent()
    const spy = vi.spyOn(agent, 'cancelRun').mockImplementation(() => {})
    const store = useAgentStore()
    const w = mountBubble()
    store.start()
    await w.vm.$nextTick()

    const stop = document.body.querySelector('.banner-stop') as HTMLElement
    expect(stop).not.toBeNull()
    stop.dispatchEvent(new Event('click', { bubbles: true }))
    await w.vm.$nextTick()

    expect(spy).toHaveBeenCalledTimes(1)
    // @click.stop on the button must not bubble to the banner's expand handler.
    expect(bubbleExpanded.value).toBe(false)
    w.unmount()
  })
})
