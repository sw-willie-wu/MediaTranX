import { ref, watch, type Ref } from 'vue'

/**
 * Per-fileId immutable-info cache with race protection.
 *
 * Invariants (spec bug4-image-switch-lag §3 — do not weaken):
 * - info(fileId) is a pure function of fileId → CACHE WRITES ALWAYS HAPPEN
 *   (responses are never aborted/discarded for the cache), only the visible
 *   `info.value` is gated by `fileId === activeFileId()` (stale-discard).
 * - fileId IS the race key (data immutable → accepting an older response for
 *   the same fileId is always correct). No monotonic request-id.
 * - `patch` replaces with a NEW object `{...prev, ...partial}` — never mutates
 *   (non-deep watchers / computed on the object must re-fire). Patching a
 *   fileId with no cached basic entry is a NO-OP (avoids partial entries).
 * - On every activeFileId change, `info.value` is set synchronously from the
 *   cache (or null) so the previous entry's data never lingers.
 */
export interface UseDomainInfoCacheOptions<T extends object> {
  activeFileId: () => string | null
  fetcher: (fileId: string) => Promise<T>
  /** LRU cap — stale entries are never *wrong* (fileIds are never reused),
   *  this is pure memory hygiene. */
  maxEntries?: number
}

export function useDomainInfoCache<T extends object>(opts: UseDomainInfoCacheOptions<T>) {
  const max = opts.maxEntries ?? 50
  const cache = new Map<string, T>()          // Map insertion order = LRU order
  const info: Ref<T | null> = ref(null)
  const isLoading = ref(false)
  const inFlight = new Set<string>()          // basic-fetch dedup per fileId

  function touch(fileId: string, value: T): void {
    cache.delete(fileId)
    cache.set(fileId, value)
    while (cache.size > max) {
      const oldest = cache.keys().next().value as string
      cache.delete(oldest)
    }
  }

  function load(fileId: string): void {
    if (inFlight.has(fileId)) return
    inFlight.add(fileId)
    opts.fetcher(fileId)
      .then((value) => {
        touch(fileId, value)                       // cache write: unconditional
        if (opts.activeFileId() === fileId) {      // visible update: guarded
          info.value = value
          isLoading.value = false
        }
      }, () => {
        // Error handler: clear isLoading if still active
        if (opts.activeFileId() === fileId) {
          isLoading.value = false
        }
        // no cache write → next visit re-fetches
      })
      .finally(() => { inFlight.delete(fileId) })
  }

  watch(opts.activeFileId, (id) => {
    // Synchronous reset — never show the previous entry's info
    const cached = id ? cache.get(id) : undefined
    if (cached !== undefined) {
      touch(id!, cached)                           // refresh LRU position
      info.value = cached
      isLoading.value = false
      return
    }
    info.value = null
    if (!id) { isLoading.value = false; return }
    isLoading.value = true
    load(id)
  }, { immediate: true })

  function patch(fileId: string, partial: Partial<T>): void {
    const prev = cache.get(fileId)
    if (prev === undefined) return               // no basic entry → no-op
    const next = { ...prev, ...partial } as T    // replace, never mutate
    touch(fileId, next)
    if (opts.activeFileId() === fileId) info.value = next
  }

  return {
    info,
    isLoading,
    patch,
    has: (fileId: string) => cache.has(fileId),
    peek: (fileId: string) => cache.get(fileId),
  }
}
