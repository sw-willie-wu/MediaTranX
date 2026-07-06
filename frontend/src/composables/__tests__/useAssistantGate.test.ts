import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAssistantGate } from '@/composables/useAssistantGate'
import { useAgentSettingsStore } from '@/stores/agentSettings'

// Hoisted spy so the test can assert what the composable pushed to the router.
const pushMock = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
}))

beforeEach(() => {
  setActivePinia(createPinia())
  pushMock.mockReset()
})

describe('useAssistantGate — redirectIfNoModel', () => {
  it('routes to the assistant settings tab and returns true when no model is selected', () => {
    // default modelChoice is '' (no model)
    const { redirectIfNoModel } = useAssistantGate()
    const intercepted = redirectIfNoModel()

    expect(intercepted).toBe(true)
    expect(pushMock).toHaveBeenCalledTimes(1)
    expect(pushMock).toHaveBeenCalledWith({ path: '/settings', query: { tab: 'agent' } })
  })

  it('does nothing and returns false when a model is selected', () => {
    const store = useAgentSettingsStore()
    store.setModelChoice('qwen3:8b:Q4_K_M')

    const { redirectIfNoModel } = useAssistantGate()
    const intercepted = redirectIfNoModel()

    expect(intercepted).toBe(false)
    expect(pushMock).not.toHaveBeenCalled()
  })
})
