import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach } from 'vitest'
import { useRemoteModelStore } from '@/stores/remoteModels'

// jsdom for localStorage (enabledIds)
// @vitest-environment jsdom

describe('remoteModels allModels reactivity (agent-picker sync)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('allModels/byCapability reflect connModels updates WITHOUT a full fetchAll (refresh syncs)', () => {
    const store = useRemoteModelStore()
    // simulate a connection that fetched empty at boot (VPN off), now enabled
    store.connections = [{ id: 1, provider: 'ollama', name: 'ttl', endpoint: 'x', enabled: true }] as any
    store.connModels[1] = []                         // boot fetch was empty
    expect(store.allModels).toHaveLength(0)

    // user opts-in a model id + "refresh" populates connModels[1]
    store.toggleEnabled('ollama:gpt-oss:20b')
    store.connModels[1] = [{ id: 'gpt-oss:20b', name: 'gpt-oss:20b', capabilities: ['text', 'tools'] }] as any

    // allModels + byCapability('tools') must now include it — no fetchAll called
    expect(store.allModels.map(m => m.modelId)).toContain('gpt-oss:20b')
    expect(store.byCapability('tools').map(m => m.modelId)).toContain('gpt-oss:20b')
  })

  it('excludes disabled connections from allModels', () => {
    const store = useRemoteModelStore()
    store.connections = [{ id: 2, provider: 'ollama', name: 'off', endpoint: 'x', enabled: false }] as any
    store.connModels[2] = [{ id: 'm', name: 'm', capabilities: ['text', 'tools'] }] as any
    expect(store.allModels).toHaveLength(0)
  })
})
