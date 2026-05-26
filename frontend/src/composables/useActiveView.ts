/**
 * useActiveView — returns the ViewHandle for the currently active route.
 *
 * Derives the viewId from the current route path, then looks it up in the
 * module-level viewRegistry.  Returns null if the route is unknown or the
 * view is not yet registered.
 *
 * Also exports `deriveViewId` as a pure function so that useActivePanel (and
 * tests) can reuse the path → viewId mapping without creating a composable.
 */
import { computed, type ComputedRef } from 'vue'
import { useRoute } from 'vue-router'
import { viewRegistry, type ViewHandle } from '@/stores/viewRegistry'

// ─── Path → viewId mapping ────────────────────────────────────────────────────

const VIEW_ID_BY_PREFIX: Array<[string, string]> = [
  ['/image',    'image'],
  ['/video',    'video'],
  ['/audio',    'audio'],
  ['/document', 'document'],
  ['/settings', 'settings'],
  ['/tasks',    'tasks'],
]

/**
 * Map a route pathname to a viewId string.
 *
 * Tries each known prefix (longest first by construction).
 * Falls back to 'home' for '/' or ''.
 * Returns null for unrecognised paths.
 */
export function deriveViewId(pathname: string): string | null {
  for (const [prefix, viewId] of VIEW_ID_BY_PREFIX) {
    if (pathname === prefix || pathname.startsWith(prefix + '/')) return viewId
  }
  if (pathname === '/' || pathname === '') return 'home'
  return null
}

// ─── Composable ───────────────────────────────────────────────────────────────

export function useActiveView(): ComputedRef<ViewHandle | null> {
  const route = useRoute()
  return computed(() => {
    const viewId = deriveViewId(route.path)
    if (!viewId) return null
    return viewRegistry.get(viewId) ?? null
  })
}
