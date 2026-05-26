import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import {
  useAgentSettingsStore,
  DEFAULT_AUTO_WHITELIST,
  DEFAULT_ALWAYS_ASK,
  AGENT_SETTINGS_KEY,
} from '../agentSettings'

// Reset localStorage and Pinia between each test to avoid state bleed
beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})

describe('useAgentSettingsStore — defaults', () => {
  it('default policy is "auto"', () => {
    const store = useAgentSettingsStore()
    expect(store.policy).toBe('auto')
  })

  it('default autoWhitelist contains all DEFAULT_AUTO_WHITELIST tools', () => {
    const store = useAgentSettingsStore()
    for (const tool of DEFAULT_AUTO_WHITELIST) {
      expect(store.autoWhitelist.has(tool)).toBe(true)
    }
    expect(store.autoWhitelist.size).toBe(DEFAULT_AUTO_WHITELIST.size)
  })

  it('default alwaysAsk contains all DEFAULT_ALWAYS_ASK tools', () => {
    const store = useAgentSettingsStore()
    for (const tool of DEFAULT_ALWAYS_ASK) {
      expect(store.alwaysAsk.has(tool)).toBe(true)
    }
    expect(store.alwaysAsk.size).toBe(DEFAULT_ALWAYS_ASK.size)
  })

  it('default modelChoice is empty string', () => {
    const store = useAgentSettingsStore()
    expect(store.modelChoice).toBe('')
  })
})

describe('shouldConfirm — policy: auto', () => {
  it('returns false for whitelisted tool', () => {
    const store = useAgentSettingsStore()
    store.setPolicy('auto')
    expect(store.shouldConfirm({ name: 'navigate_to' })).toBe(false)
  })

  it('returns true for non-whitelisted tool', () => {
    const store = useAgentSettingsStore()
    store.setPolicy('auto')
    expect(store.shouldConfirm({ name: 'unknown_tool' })).toBe(true)
  })
})

describe('shouldConfirm — policy: ask_all', () => {
  it('returns true even for whitelisted tool', () => {
    const store = useAgentSettingsStore()
    store.setPolicy('ask_all')
    expect(store.shouldConfirm({ name: 'navigate_to' })).toBe(true)
  })

  it('returns true for any tool', () => {
    const store = useAgentSettingsStore()
    store.setPolicy('ask_all')
    expect(store.shouldConfirm({ name: 'execute' })).toBe(true)
    expect(store.shouldConfirm({ name: 'add_file' })).toBe(true)
    expect(store.shouldConfirm({ name: 'some_random' })).toBe(true)
  })
})

describe('shouldConfirm — policy: custom', () => {
  it('returns false for tool in autoWhitelist', () => {
    const store = useAgentSettingsStore()
    store.setPolicy('custom')
    expect(store.shouldConfirm({ name: 'navigate_to' })).toBe(false)
  })

  it('returns true for tool in alwaysAsk', () => {
    const store = useAgentSettingsStore()
    store.setPolicy('custom')
    expect(store.shouldConfirm({ name: 'add_file' })).toBe(true)
  })

  it('returns false for tool in neither list (custom → auto-deny, no prompt)', () => {
    const store = useAgentSettingsStore()
    store.setPolicy('custom')
    // Remove from whitelist and not in alwaysAsk
    store.removeFromWhitelist('navigate_to')
    expect(store.shouldConfirm({ name: 'navigate_to' })).toBe(false)
  })

  it('uses panelSchema.execute.requiresConfirm for "execute" tool when not in any list', () => {
    const store = useAgentSettingsStore()
    store.setPolicy('custom')
    // 'execute' is in alwaysAsk by default, remove it to test panel fallback
    store.removeFromAlwaysAsk('execute')
    // Also ensure it's not in autoWhitelist
    expect(store.autoWhitelist.has('execute')).toBe(false)

    const schema = { execute: { requiresConfirm: true } }
    expect(store.shouldConfirm({ name: 'execute' }, schema)).toBe(true)

    const schema2 = { execute: { requiresConfirm: false } }
    expect(store.shouldConfirm({ name: 'execute' }, schema2)).toBe(false)
  })
})

describe('Set mutators — reassign-Set pattern (m2)', () => {
  it('addToWhitelist creates a new Set instance', () => {
    const store = useAgentSettingsStore()
    const before = store.autoWhitelist
    store.addToWhitelist('new_tool')
    expect(store.autoWhitelist).not.toBe(before)
    expect(store.autoWhitelist.has('new_tool')).toBe(true)
  })

  it('removeFromWhitelist creates a new Set instance', () => {
    const store = useAgentSettingsStore()
    const before = store.autoWhitelist
    store.removeFromWhitelist('navigate_to')
    expect(store.autoWhitelist).not.toBe(before)
    expect(store.autoWhitelist.has('navigate_to')).toBe(false)
  })

  it('addToAlwaysAsk creates a new Set instance', () => {
    const store = useAgentSettingsStore()
    const before = store.alwaysAsk
    store.addToAlwaysAsk('some_tool')
    expect(store.alwaysAsk).not.toBe(before)
    expect(store.alwaysAsk.has('some_tool')).toBe(true)
  })

  it('removeFromAlwaysAsk creates a new Set instance', () => {
    const store = useAgentSettingsStore()
    const before = store.alwaysAsk
    store.removeFromAlwaysAsk('execute')
    expect(store.alwaysAsk).not.toBe(before)
    expect(store.alwaysAsk.has('execute')).toBe(false)
  })
})

describe('hydrate — from empty localStorage', () => {
  it('keeps all defaults when localStorage is empty', () => {
    const store = useAgentSettingsStore()
    expect(store.policy).toBe('auto')
    expect(store.autoWhitelist.size).toBe(DEFAULT_AUTO_WHITELIST.size)
    expect(store.alwaysAsk.size).toBe(DEFAULT_ALWAYS_ASK.size)
  })
})

describe('hydrate — from stored data', () => {
  it('restores policy and modelChoice', () => {
    localStorage.setItem(AGENT_SETTINGS_KEY, JSON.stringify({
      policy: 'ask_all',
      modelChoice: 'gpt-4o',
      autoWhitelist: ['navigate_to'],
      alwaysAsk: ['execute'],
      userRemovedTools: [],
    }))
    const store = useAgentSettingsStore()
    expect(store.policy).toBe('ask_all')
    expect(store.modelChoice).toBe('gpt-4o')
  })

  it('restores stored whitelist merged with defaults (m3: no userRemovedTools)', () => {
    // Store a whitelist that has one custom tool and is missing some defaults
    localStorage.setItem(AGENT_SETTINGS_KEY, JSON.stringify({
      policy: 'auto',
      autoWhitelist: ['navigate_to', 'my_custom_tool'],
      alwaysAsk: [],
      userRemovedTools: [],
    }))
    const store = useAgentSettingsStore()
    // Should have: union(stored, DEFAULTS) - userRemovedTools
    expect(store.autoWhitelist.has('my_custom_tool')).toBe(true)
    // Missing defaults get added back (m3 migration)
    for (const t of DEFAULT_AUTO_WHITELIST) {
      expect(store.autoWhitelist.has(t)).toBe(true)
    }
  })
})

describe('m3 migration: union(stored, DEFAULTS) - userRemovedTools', () => {
  it('does NOT re-add tools that user explicitly removed', () => {
    // User previously removed 'navigate_to' from the whitelist
    localStorage.setItem(AGENT_SETTINGS_KEY, JSON.stringify({
      policy: 'auto',
      autoWhitelist: ['get_panel_state'],  // navigate_to is absent
      alwaysAsk: ['execute', 'add_file'],
      userRemovedTools: ['navigate_to'],
    }))
    const store = useAgentSettingsStore()
    // navigate_to is in DEFAULT_AUTO_WHITELIST but user removed it → must stay out
    expect(store.autoWhitelist.has('navigate_to')).toBe(false)
  })

  it('adds new default tools not tracked in userRemovedTools', () => {
    // Simulate a user who stored settings before 'set_view_function' was a default
    localStorage.setItem(AGENT_SETTINGS_KEY, JSON.stringify({
      policy: 'auto',
      autoWhitelist: ['navigate_to', 'get_panel_state'],
      alwaysAsk: ['execute', 'add_file'],
      userRemovedTools: [],
    }))
    const store = useAgentSettingsStore()
    // All current defaults should be present (new ones added by migration)
    for (const t of DEFAULT_AUTO_WHITELIST) {
      expect(store.autoWhitelist.has(t)).toBe(true)
    }
  })
})

describe('persist — writes to localStorage on mutation', () => {
  it('persist() writes the agent_settings key', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem')
    const store = useAgentSettingsStore()
    store.persist()
    expect(spy).toHaveBeenCalledWith(AGENT_SETTINGS_KEY, expect.any(String))
    spy.mockRestore()
  })

  it('localStorage key is "agent_settings"', () => {
    const store = useAgentSettingsStore()
    store.setPolicy('ask_all')
    // Flush microtasks so watch fires
    const raw = localStorage.getItem(AGENT_SETTINGS_KEY)
    // persist() called in watch — may not have fired yet in sync test;
    // call manually to verify key name
    store.persist()
    const raw2 = localStorage.getItem(AGENT_SETTINGS_KEY)
    expect(raw2).not.toBeNull()
    const parsed = JSON.parse(raw2!)
    expect(parsed.policy).toBe('ask_all')
    void raw  // suppress unused warning
  })

  it('persisted JSON contains all expected fields', () => {
    const store = useAgentSettingsStore()
    store.setPolicy('custom')
    store.setModelChoice('claude-sonnet')
    store.persist()
    const parsed = JSON.parse(localStorage.getItem(AGENT_SETTINGS_KEY)!)
    expect(parsed).toHaveProperty('policy', 'custom')
    expect(parsed).toHaveProperty('modelChoice', 'claude-sonnet')
    expect(parsed).toHaveProperty('autoWhitelist')
    expect(parsed).toHaveProperty('alwaysAsk')
    expect(parsed).toHaveProperty('userRemovedTools')
    expect(Array.isArray(parsed.autoWhitelist)).toBe(true)
  })
})
