/**
 * agentNavCatalog — single static source of truth for the agent's "site map":
 * which top-level views exist and what sub-functions each offers.
 *
 * Consumed by:
 *  - the 5 *View.vue components (validSubfunctions) — replaces per-view literals
 *  - useAgentState.buildAgentStateSnapshot() — to build snapshot.map.views
 *
 * Subfunction ids are kept in the kebab "routing" namespace exactly as the
 * views/select_subfunction expect (e.g. 'remove-bg', 'pdf-convert'). Do NOT
 * normalize to underscore here — panelIdFor() does that at the panel-lookup seam.
 */
export interface NavCatalogEntry {
  viewId: string
  route: string
  label: string
  subfunctions: string[]
}

export const AGENT_NAV_CATALOG: NavCatalogEntry[] = [
  { viewId: 'image',    route: '/image',    label: 'Image',
    subfunctions: ['transcode','compress','adjust','filter','crop','remove-bg','ai-remove','upscale','ocr'] },
  { viewId: 'video',    route: '/video',    label: 'Video',
    subfunctions: ['transcode','cut','crop','subtitle','summary','interpolate','enhance'] },
  { viewId: 'audio',    route: '/audio',    label: 'Audio',
    subfunctions: ['transcode','cut','volume','midi-edit','transcribe','separate','lyrics'] },
  { viewId: 'document', route: '/document', label: 'Document',
    subfunctions: ['split','pdf-convert','ocr','translate'] },
  { viewId: 'settings', route: '/settings', label: 'Settings',
    subfunctions: ['general','system','models','agent','video-download','about'] },
  { viewId: 'tasks',    route: '/tasks',    label: 'Tasks',    subfunctions: [] },
  { viewId: 'home',     route: '/',         label: 'Home',     subfunctions: [] },
]

const _BY_VIEW_ID = new Map(AGENT_NAV_CATALOG.map(e => [e.viewId, e]))

/** Subfunctions for a viewId; [] for unknown / subfunction-less views. */
export function subfunctionsForView(viewId: string): string[] {
  return _BY_VIEW_ID.get(viewId)?.subfunctions ?? []
}

/** Route for a viewId; null for unknown. Used by the snapshot builder to map
 *  the active panel's viewId (panelId.split('.')[0]) → current_position.view. */
export function routeForView(viewId: string): string | null {
  return _BY_VIEW_ID.get(viewId)?.route ?? null
}
