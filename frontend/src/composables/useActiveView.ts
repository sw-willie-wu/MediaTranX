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

/**
 * Build the canonical panel-registry key for a (viewId, subfunction) pair.
 *
 * Subfunction ids live in the kebab "routing" namespace (`remove-bg`,
 * `pdf-convert` — mirroring the HTTP route convention), but panels register
 * under the snake "data-identity" namespace (`image.remove_bg`, matching
 * taskType / i18n keys). The agent bridge is the single point where the two
 * namespaces meet, so hyphens are normalized to underscores here. Without
 * this, every multi-word subfunction resolves to null →
 * agent.error.panel_not_supported. Single-word subfunctions (upscale /
 * adjust / ocr) are unaffected (no-op).
 */
export function panelIdFor(viewId: string, fn: string): string {
  return `${viewId}.${fn.replace(/-/g, '_')}`
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
