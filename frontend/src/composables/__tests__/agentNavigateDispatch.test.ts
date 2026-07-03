// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAgentStore } from '@/stores/agent'

// navigate_to's dispatcher (outside setup) reaches the router via import('@/router').
// The real global singleton's push('/video') triggers a real lazy-import of
// VideoView.vue (+ its whole panel tree) — seconds under parallel load, tripping
// the 5s test timeout. A fast fake keeps the dispatch logic under test (route
// resolve-validation + setCurrentAction + push) without the heavy import.
const push = vi.fn().mockResolvedValue(undefined)
vi.mock('@/router', () => ({
  default: {
    resolve: (path: string) => ({ matched: [{ path }] }), // any path is a matched route
    push,
    currentRoute: { value: { path: '/' } },
  },
}))

beforeEach(() => {
  setActivePinia(createPinia())
  push.mockClear()
})

describe('navigate_to dispatch', () => {
  it('sets the banner action key before navigating, validates the route, returns ok', async () => {
    const { dispatch } = await import('@/composables/useAgentTools')
    const store = useAgentStore()
    const result = await dispatch({
      id: 'tc1', type: 'function',
      function: { name: 'navigate_to', arguments: '{"route":"/video"}' },
    })
    expect(store.currentAction.key).toBe('agent.banner.act.navigate_to')
    expect(store.currentAction.args).toEqual({ route: '/video' })
    expect(result.ok).toBe(true)
    expect(push).toHaveBeenCalledWith('/video')
  })
})
