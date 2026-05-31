import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAgentStore } from '../agent'

describe('useAgentStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  // ─── isRunning ─────────────────────────────────────────────────────────────

  it('starts with isRunning = false', () => {
    const store = useAgentStore()
    expect(store.isRunning).toBe(false)
  })

  it('start() sets isRunning to true', () => {
    const store = useAgentStore()
    store.start()
    expect(store.isRunning).toBe(true)
  })

  it('stop() sets isRunning to false after start', () => {
    const store = useAgentStore()
    store.start()
    store.stop()
    expect(store.isRunning).toBe(false)
  })

  // ─── currentAction ─────────────────────────────────────────────────────────

  it('setCurrentAction stores key and args', () => {
    const store = useAgentStore()
    store.setCurrentAction('agent.banner.act.navigate_to', { route: '/video' })
    expect(store.currentAction.key).toBe('agent.banner.act.navigate_to')
    expect(store.currentAction.args).toEqual({ route: '/video' })
  })

  it('setCurrentAction defaults args to empty object', () => {
    const store = useAgentStore()
    store.setCurrentAction('agent.banner.act.thinking')
    expect(store.currentAction.args).toEqual({})
  })

  // ─── Token accounting (M21 B4) ─────────────────────────────────────────────

  it('addUsage: prompt REPLACES, completion ACCUMULATES', () => {
    const store = useAgentStore()

    store.addUsage({ promptTokens: 100, completionTokens: 50 })
    expect(store.threadTokens.prompt).toBe(100)
    expect(store.threadTokens.completion).toBe(50)

    // Second call: prompt replaces (200 > 100 because full history re-sent),
    // completion accumulates (50 + 30 = 80)
    store.addUsage({ promptTokens: 200, completionTokens: 30 })
    expect(store.threadTokens.prompt).toBe(200)      // REPLACE
    expect(store.threadTokens.completion).toBe(80)   // ACCUMULATE
  })

  it('addUsage: missing promptTokens keeps previous prompt value', () => {
    const store = useAgentStore()
    store.addUsage({ promptTokens: 100, completionTokens: 10 })
    store.addUsage({ completionTokens: 20 })  // no promptTokens
    expect(store.threadTokens.prompt).toBe(100)     // unchanged
    expect(store.threadTokens.completion).toBe(30)  // accumulated
  })

  it('addUsage: missing completionTokens adds zero', () => {
    const store = useAgentStore()
    store.addUsage({ promptTokens: 50 })
    expect(store.threadTokens.completion).toBe(0)
  })

  it('addUsage: undefined usage is a no-op', () => {
    const store = useAgentStore()
    store.addUsage(undefined)
    expect(store.threadTokens.prompt).toBe(0)
    expect(store.threadTokens.completion).toBe(0)
  })

  it('resetTokens() zeroes both prompt and completion', () => {
    const store = useAgentStore()
    store.addUsage({ promptTokens: 100, completionTokens: 200 })
    store.resetTokens()
    expect(store.threadTokens.prompt).toBe(0)
    expect(store.threadTokens.completion).toBe(0)
  })

  // ─── Transient buffer ──────────────────────────────────────────────────────

  it('setTransient stores the buffer', () => {
    const store = useAgentStore()
    const buf = {
      messageId: 'msg-1',
      text: 'hello',
      toolCallsBuf: new Map(),
    }
    store.setTransient(buf)
    // Pinia wraps the value in a reactive proxy, so compare by deep equality
    expect(store.transient).toStrictEqual(buf)
    expect(store.transient?.messageId).toBe('msg-1')
    expect(store.transient?.text).toBe('hello')
  })

  it('clearTransient sets transient to null', () => {
    const store = useAgentStore()
    store.setTransient({ messageId: 'x', text: '', toolCallsBuf: new Map() })
    store.clearTransient()
    expect(store.transient).toBeNull()
  })

  // ─── Pending confirms ──────────────────────────────────────────────────────

  it('resolveAllPendingConfirms calls each resolver with false and clears the set', () => {
    const store = useAgentStore()
    const calls: boolean[] = []
    const r1 = (v: boolean) => calls.push(v)
    const r2 = (v: boolean) => calls.push(v)

    store.addPendingConfirm(r1)
    store.addPendingConfirm(r2)
    store.resolveAllPendingConfirms(false)

    expect(calls).toEqual([false, false])
    expect(store.pendingConfirms.size).toBe(0)
  })

  it('resolveAllPendingConfirms(true) calls resolvers with true', () => {
    const store = useAgentStore()
    let received: boolean | null = null
    store.addPendingConfirm((v) => { received = v })
    store.resolveAllPendingConfirms(true)
    expect(received).toBe(true)
  })

  it('addPendingConfirm reassigns Set (ref identity changes)', () => {
    const store = useAgentStore()
    const before = store.pendingConfirms
    store.addPendingConfirm(() => {})
    // The Set ref should point to a new Set instance (reassign-Set pattern)
    expect(store.pendingConfirms).not.toBe(before)
  })

  it('removePendingConfirm removes only the specified resolver', () => {
    const store = useAgentStore()
    const r1 = () => {}
    const r2 = () => {}
    store.addPendingConfirm(r1)
    store.addPendingConfirm(r2)
    store.removePendingConfirm(r1)
    expect(store.pendingConfirms.has(r1)).toBe(false)
    expect(store.pendingConfirms.has(r2)).toBe(true)
  })
})
