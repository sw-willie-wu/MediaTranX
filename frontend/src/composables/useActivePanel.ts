/**
 * useActivePanel — returns the currently active panel entry.
 *
 * Composes `deriveViewId` (from useActiveView) + the active view's
 * `currentFunction` ref to build the canonical `viewId.fn` panel id, then
 * looks it up in the module-level panelRegistry.
 *
 * Returns null when:
 *   - the current route is unrecognised
 *   - the view is not registered (e.g. not yet mounted)
 *   - the view has no currentFunction set
 *   - no panel is registered under `viewId.currentFunction`
 */
import { computed, type ComputedRef } from 'vue'
import { useRoute } from 'vue-router'
import { deriveViewId, useActiveView } from '@/composables/useActiveView'
import { panelRegistry, type PanelHandle, type PanelAgentSchema } from '@/stores/panelRegistry'

// ─── Public types ─────────────────────────────────────────────────────────────

export interface ActivePanelEntry {
  panelId: string
  schema: PanelAgentSchema
  instance: PanelHandle
  isMounted: boolean
}

// ─── Composable ───────────────────────────────────────────────────────────────

export function useActivePanel(): ComputedRef<ActivePanelEntry | null> {
  const route = useRoute()
  const activeView = useActiveView()

  return computed(() => {
    const viewId = deriveViewId(route.path)
    if (!viewId) return null

    const view = activeView.value
    if (!view) return null

    const fn = view.currentFunction.value
    if (!fn) return null

    const panelId = `${viewId}.${fn}`
    const entry = panelRegistry.get(panelId)
    if (!entry) return null

    return {
      panelId,
      schema: entry.agentSchema,
      instance: entry,
      isMounted: entry.isMounted.value,
    }
  })
}
