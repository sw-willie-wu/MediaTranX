/**
 * Tests for usePersistedModel `enabled` option (unified-param-components batch 1, Task 1.4)
 *
 * Covers:
 *   1. enabled=true (default) — seeds from localStorage and persists writes (unchanged behavior)
 *   2. no options arg at all — unchanged behavior (backward compat for existing callers)
 *   3. enabled=false — does NOT seed from localStorage (uses fallback), does NOT persist writes
 *   4. enabled as a ref that starts false — no seed; existing localStorage value untouched
 */

import { ref, nextTick } from 'vue'
import { describe, it, expect, beforeEach } from 'vitest'
import { usePersistedModel } from '@/composables/usePersistedModel'

describe('usePersistedModel', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('enabled=true (default): seeds from localStorage and persists writes', async () => {
    localStorage.setItem('k1', 'saved-value')
    const value = usePersistedModel('k1', 'fallback')
    expect(value.value).toBe('saved-value')

    value.value = 'new-value'
    await nextTick()
    expect(localStorage.getItem('k1')).toBe('new-value')
  })

  it('no options arg: behaves exactly as before (backward compat)', async () => {
    const value = usePersistedModel('k2', 'fallback')
    expect(value.value).toBe('fallback')

    value.value = 'written'
    await nextTick()
    expect(localStorage.getItem('k2')).toBe('written')
  })

  it('enabled=false: does not seed from localStorage, uses fallback', () => {
    localStorage.setItem('k3', 'saved-value')
    const value = usePersistedModel('k3', 'fallback', { enabled: false })
    expect(value.value).toBe('fallback')
  })

  it('enabled=false: does not persist writes to localStorage', async () => {
    const value = usePersistedModel('k4', 'fallback', { enabled: false })
    value.value = 'changed'
    await nextTick()
    expect(localStorage.getItem('k4')).toBeNull()
  })

  it('enabled as a ref starting false: no seed; toggling later does not retroactively seed', async () => {
    localStorage.setItem('k5', 'saved-value')
    const enabled = ref(false)
    const value = usePersistedModel('k5', 'fallback', { enabled })
    expect(value.value).toBe('fallback')

    value.value = 'still-not-written'
    await nextTick()
    expect(localStorage.getItem('k5')).toBe('saved-value')

    enabled.value = true
    value.value = 'now-written'
    await nextTick()
    expect(localStorage.getItem('k5')).toBe('now-written')
  })
})
