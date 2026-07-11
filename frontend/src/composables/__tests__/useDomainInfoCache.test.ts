import { describe, it, expect, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import { useDomainInfoCache } from '@/composables/useDomainInfoCache'

interface Info { width: number; palette?: number }

/** Controllable fetcher: resolve/reject each call by fileId, count dispatches. */
function makeFetcher() {
  const pending = new Map<string, { resolve: (v: Info) => void; reject: (e: unknown) => void }[]>()
  const calls: string[] = []
  const fetcher = vi.fn((id: string) => {
    calls.push(id)
    return new Promise<Info>((resolve, reject) => {
      const list = pending.get(id) ?? []
      list.push({ resolve, reject })
      pending.set(id, list)
    })
  })
  const settle = (id: string, v: Info) => { pending.get(id)!.shift()!.resolve(v); return nextTick() }
  const fail = (id: string) => { pending.get(id)!.shift()!.reject(new Error('x')); return nextTick() }
  return { fetcher, settle, fail, calls }
}

function setup(maxEntries?: number) {
  const active = ref<string | null>(null)
  const f = makeFetcher()
  const cacheApi = useDomainInfoCache<Info>({
    activeFileId: () => active.value,
    fetcher: f.fetcher,
    maxEntries,
  })
  return { active, ...f, ...cacheApi }
}

describe('useDomainInfoCache', () => {
  it('① cache hit does not fetch again (0 network on revisit)', async () => {
    const s = setup()
    s.active.value = 'A'; await nextTick()
    await s.settle('A', { width: 10 })
    s.active.value = 'B'; await nextTick()
    await s.settle('B', { width: 20 })
    s.active.value = 'A'; await nextTick()
    expect(s.calls).toEqual(['A', 'B'])          // no 3rd fetch
    expect(s.info.value).toEqual({ width: 10 })  // instant from cache
  })

  it('② stale response does NOT update info.value but DOES write cache', async () => {
    const s = setup()
    s.active.value = 'A'; await nextTick()
    s.active.value = 'B'; await nextTick()
    await s.settle('A', { width: 10 })   // A resolves while B active
    expect(s.info.value).toBeNull()      // B still in flight → visible stays null
    expect(s.peek('A')).toEqual({ width: 10 })  // but cache written
    await s.settle('B', { width: 20 })
    expect(s.info.value).toEqual({ width: 20 })
    s.active.value = 'A'; await nextTick()
    expect(s.info.value).toEqual({ width: 10 }) // cache hit, complete data
  })

  it('③ patch while switched away writes cache; revisit shows patched value', async () => {
    const s = setup()
    s.active.value = 'A'; await nextTick()
    await s.settle('A', { width: 10 })
    s.active.value = 'B'; await nextTick()
    s.patch('A', { palette: 5 })                 // arrives while B active
    expect(s.peek('A')).toEqual({ width: 10, palette: 5 })
    await s.settle('B', { width: 20 })
    s.active.value = 'A'; await nextTick()
    expect(s.info.value).toEqual({ width: 10, palette: 5 })
  })

  it('④ rapid A→B→A while A basic in flight does not lose A (re-entry tolerated, final state correct)', async () => {
    const s = setup()
    s.active.value = 'A'; await nextTick()
    s.active.value = 'B'; await nextTick()
    s.active.value = 'A'; await nextTick()       // back while A(first) unresolved
    await s.settle('A', { width: 10 })           // first response lands
    expect(s.info.value).toEqual({ width: 10 }) // fileId is the race key → accepted
  })

  it('⑤ info.value resets synchronously on switch (no stale from previous entry)', async () => {
    const s = setup()
    s.active.value = 'A'; await nextTick()
    await s.settle('A', { width: 10 })
    s.active.value = 'B'; await nextTick()
    expect(s.info.value).toBeNull()              // uncached B → null, not A's data
    s.active.value = null; await nextTick()
    expect(s.info.value).toBeNull()
  })

  it('⑥ patch onto unknown/evicted fileId is a no-op (no partial entry)', async () => {
    const s = setup()
    s.patch('ghost', { palette: 5 })
    expect(s.peek('ghost')).toBeUndefined()
    expect(s.has('ghost')).toBe(false)
  })

  it('⑦ LRU cap evicts oldest beyond maxEntries', async () => {
    const s = setup(2)
    for (const id of ['A', 'B', 'C']) {
      s.active.value = id; await nextTick()
      await s.settle(id, { width: 1 })
    }
    expect(s.has('A')).toBe(false)
    expect(s.has('B')).toBe(true)
    expect(s.has('C')).toBe(true)
  })

  it('⑧ fetcher rejection clears isLoading and allows re-fetch on revisit', async () => {
    const s = setup()
    s.active.value = 'A'; await nextTick()
    await s.fail('A')
    expect(s.isLoading.value).toBe(false)
    expect(s.has('A')).toBe(false)
    s.active.value = 'B'; await nextTick()
    await s.settle('B', { width: 20 })
    s.active.value = 'A'; await nextTick()       // revisit → cache miss → re-fetch
    expect(s.calls.filter(c => c === 'A').length).toBe(2)
  })
})
